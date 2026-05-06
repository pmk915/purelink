import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const API_BASE_URL = process.env.PURELINK_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

type TokenResponse = {
  access_token: string;
  token_type: string;
};

type KnowledgeBase = {
  id: number;
  name: string;
};

type DocumentRead = {
  id: number;
  original_filename: string;
  processing_status: string;
  latest_processing_job_status: string | null;
  latest_processing_job_step: string | null;
  latest_processing_job_error_code: string | null;
  error_message: string | null;
};

type AskResponse = {
  conversation_id: number;
  answer: string;
  citations: Array<{ citation_marker?: string | null }>;
  intent?: string | null;
};

type ConversationRead = {
  id: number;
  messages: Array<{
    id: number;
    role: "system" | "user" | "assistant";
    content: string;
    citations: Array<{ citation_marker?: string | null }>;
  }>;
};

type AuthUser = {
  username: string;
  password: string;
};

function authHeaders(token: string) {
  return {
    Authorization: `Bearer ${token}`
  };
}

async function registerAndLogin(request: APIRequestContext): Promise<AuthUser & { token: string }> {
  const seed = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const username = `e2e_${seed}`;
  const email = `${username}@example.com`;
  const password = "PureLinkE2E123!";

  const registerResponse = await request.post(`${API_BASE_URL}/auth/register`, {
    data: {
      email,
      username,
      password
    }
  });
  expect(registerResponse.ok()).toBeTruthy();

  const loginResponse = await request.post(`${API_BASE_URL}/auth/login`, {
    data: {
      identifier: username,
      password
    }
  });
  expect(loginResponse.ok()).toBeTruthy();
  const tokenPayload = (await loginResponse.json()) as TokenResponse;

  return {
    username,
    password,
    token: tokenPayload.access_token
  };
}

async function createKnowledgeBase(
  request: APIRequestContext,
  token: string,
  name: string
): Promise<KnowledgeBase> {
  const response = await request.post(`${API_BASE_URL}/knowledge-bases`, {
    headers: authHeaders(token),
    data: {
      name,
      description: "Playwright browser follow-up regression test knowledge base."
    }
  });
  expect(response.ok()).toBeTruthy();
  return (await response.json()) as KnowledgeBase;
}

async function uploadTextDocument(
  request: APIRequestContext,
  token: string,
  knowledgeBaseId: number,
  filename: string,
  content: string
): Promise<DocumentRead> {
  const response = await request.post(
    `${API_BASE_URL}/knowledge-bases/${knowledgeBaseId}/documents`,
    {
      headers: authHeaders(token),
      multipart: {
        file: {
          name: filename,
          mimeType: "text/plain",
          buffer: Buffer.from(content, "utf-8")
        }
      }
    }
  );
  expect(response.ok()).toBeTruthy();
  return (await response.json()) as DocumentRead;
}

async function listDocuments(
  request: APIRequestContext,
  token: string,
  knowledgeBaseId: number
): Promise<DocumentRead[]> {
  const response = await request.get(`${API_BASE_URL}/knowledge-bases/${knowledgeBaseId}/documents`, {
    headers: authHeaders(token)
  });
  expect(response.ok()).toBeTruthy();
  return (await response.json()) as DocumentRead[];
}

async function waitForIndexedDocument(
  request: APIRequestContext,
  token: string,
  knowledgeBaseId: number,
  documentId: number
): Promise<DocumentRead> {
  const deadline = Date.now() + 2 * 60 * 1000;

  while (Date.now() < deadline) {
    const documents = await listDocuments(request, token, knowledgeBaseId);
    const document = documents.find((item) => item.id === documentId);

    if (!document) {
      throw new Error(`Document ${documentId} not found while waiting for indexed status.`);
    }

    if (document.processing_status === "indexed") {
      return document;
    }

    if (document.processing_status === "failed") {
      throw new Error(
        `Document ${documentId} failed: status=${document.processing_status} step=${document.latest_processing_job_step} error_code=${document.latest_processing_job_error_code} message=${document.error_message}`
      );
    }

    await new Promise((resolve) => setTimeout(resolve, 2000));
  }

  throw new Error(`Document ${documentId} did not reach indexed within timeout.`);
}

async function askKnowledgeBase(
  request: APIRequestContext,
  token: string,
  knowledgeBaseId: number,
  question: string
): Promise<AskResponse> {
  const response = await request.post(`${API_BASE_URL}/knowledge-bases/${knowledgeBaseId}/ask`, {
    headers: authHeaders(token),
    data: {
      question,
      top_k: 5
    }
  });
  expect(response.ok()).toBeTruthy();
  return (await response.json()) as AskResponse;
}

async function getConversation(
  request: APIRequestContext,
  token: string,
  conversationId: number
): Promise<ConversationRead> {
  const response = await request.get(`${API_BASE_URL}/conversations/${conversationId}`, {
    headers: authHeaders(token)
  });
  expect(response.ok()).toBeTruthy();
  return (await response.json()) as ConversationRead;
}

async function loginThroughUi(page: Page, user: AuthUser) {
  await page.goto("/login");
  await page.getByTestId("login-identifier").fill(user.username);
  await page.getByTestId("login-password").fill(user.password);
  await Promise.all([
    page.waitForURL((url) => !url.pathname.startsWith("/login")),
    page.getByTestId("login-submit").click()
  ]);
}

async function waitForMessageCount(page: Page, count: number) {
  await expect
    .poll(async () => page.getByTestId("conversation-message-item").count())
    .toBe(count);
}

async function sendFollowUp(page: Page, question: string) {
  await page.getByTestId("conversation-question-input").fill(question);
  await page.getByTestId("conversation-question-submit").click();
}

async function expectLatestAssistantMessageWithSources(page: Page) {
  const latestAssistantMessage = page
    .locator('[data-testid="conversation-message-item"][data-message-role="assistant"]')
    .last();

  await expect(latestAssistantMessage).toContainText(/\[S\d+\]/);

  const sourceToggle = latestAssistantMessage.locator('[data-testid^="conversation-sources-toggle-"]');
  await expect(sourceToggle).toBeVisible();
  await sourceToggle.click();

  await expect(latestAssistantMessage.getByTestId("citation-card").first()).toBeVisible();
}

test("browser follow-up keeps appending inside the same conversation and survives refresh", async ({
  page,
  request
}) => {
  const user = await registerAndLogin(request);
  const knowledgeBase = await createKnowledgeBase(
    request,
    user.token,
    `PureLink Conversation Follow-up ${Date.now()}`
  );

  const docA = await uploadTextDocument(
    request,
    user.token,
    knowledgeBase.id,
    "usagi-profile-a.txt",
    [
      "乌萨奇是《吉伊卡哇》系列中的角色。",
      "乌萨奇的名字就叫乌萨奇。",
      "乌萨奇是明黄色的小兔子，有粉色内耳。",
      "这份资料重点介绍乌萨奇的身份和外貌。"
    ].join("\n")
  );
  const docB = await uploadTextDocument(
    request,
    user.token,
    knowledgeBase.id,
    "usagi-profile-b.txt",
    [
      "这个知识库主要整理乌萨奇的设定、作品背景和常见特征。",
      "资料提到乌萨奇经常和其他角色一起出现，也强调了它的角色背景。",
      "这些文档覆盖身份、外貌和设定三个方面。"
    ].join("\n")
  );

  await waitForIndexedDocument(request, user.token, knowledgeBase.id, docA.id);
  await waitForIndexedDocument(request, user.token, knowledgeBase.id, docB.id);

  const initialAsk = await askKnowledgeBase(request, user.token, knowledgeBase.id, "乌萨奇是谁？");
  expect(initialAsk.answer).not.toEqual("");
  expect(initialAsk.citations.length).toBeGreaterThan(0);

  const seededConversation = await getConversation(request, user.token, initialAsk.conversation_id);
  expect(seededConversation.messages).toHaveLength(2);

  await loginThroughUi(page, user);
  await page.goto(`/conversations/${initialAsk.conversation_id}`);
  await expect(page.getByTestId("conversation-thread-page")).toBeVisible();
  await waitForMessageCount(page, 2);

  const factFollowUp = "那它叫什么名字？";
  await sendFollowUp(page, factFollowUp);
  await waitForMessageCount(page, 4);
  await expect(page).toHaveURL(new RegExp(`/conversations/${initialAsk.conversation_id}$`));
  await expect(page.getByText(factFollowUp, { exact: true })).toBeVisible();
  await expectLatestAssistantMessageWithSources(page);

  await page.reload();
  await expect(page.getByTestId("conversation-thread-page")).toBeVisible();
  await waitForMessageCount(page, 4);
  await expect(page.getByText(factFollowUp, { exact: true })).toBeVisible();

  const overviewFollowUp = "总结这个知识库的主要内容";
  await sendFollowUp(page, overviewFollowUp);
  await waitForMessageCount(page, 6);
  await expect(page).toHaveURL(new RegExp(`/conversations/${initialAsk.conversation_id}$`));
  await expect(page.getByText(overviewFollowUp, { exact: true })).toBeVisible();
  await expectLatestAssistantMessageWithSources(page);

  await page.reload();
  await expect(page.getByTestId("conversation-thread-page")).toBeVisible();
  await waitForMessageCount(page, 6);
  await expect(page.getByText(overviewFollowUp, { exact: true })).toBeVisible();

  const refreshedConversation = await getConversation(request, user.token, initialAsk.conversation_id);
  expect(refreshedConversation.messages).toHaveLength(6);
  expect(refreshedConversation.messages.at(-1)?.role).toBe("assistant");
  expect(refreshedConversation.messages.at(-1)?.citations.length ?? 0).toBeGreaterThan(0);
});
