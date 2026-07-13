import { expect, test, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";
import path from "node:path";

import { parseCitationMarkers } from "@/lib/citation-markers";
import { citationSchema } from "@/schemas/qa";

const API_PATTERN = "**/api/v1/**";

const readyCitation = citationSchema.parse({
  citation_marker: "S1",
  citation_unit_id: 101,
  chunk_id: "10:0",
  document_id: 10,
  knowledge_base_id: 7,
  scope: "personal",
  team_id: null,
  document_name: "retrieval-guide.txt",
  text: "The final evidence explains how citation markers map to persisted source units.",
  snippet: "The final evidence explains citation markers.",
  source_type: "text",
  source_locator: {
    kind: "text_range",
    document_id: 10,
    source_type: "text",
    source_locator_text: "section:Citation contract",
    char_start: 24,
    char_end: 98,
    section_title: "Citation contract",
    heading_path: ["Retrieval", "Citation contract"]
  },
  preview_target: {
    kind: "document_preview",
    document_id: 10,
    source_type: "text",
    locator_kind: "text_range",
    source_locator_text: "section:Citation contract",
    char_start: 24,
    char_end: 98,
    section_title: "Citation contract"
  },
  heading_path: ["Retrieval", "Citation contract"],
  section_title: "Citation contract",
  char_start: 24,
  char_end: 98,
  citation_ready: true,
  retrieval_mode: "hybrid_text",
  score: 0.84
});

const limitedCitation = citationSchema.parse({
  citation_marker: "S2",
  document_name: null,
  text: "Legacy evidence remains readable even when detailed provenance is unavailable.",
  source_type: "text",
  source_locator: null,
  heading_path: [],
  citation_ready: false,
  retrieval_mode: null,
  score: null
});

const assistantAnswer =
  "Canonical [S1], repeated [S1], and legacy [1]. Unknown [S99] and [ordinary] remain text. Limited [S2]. Link [S1](https://example.com).";

test("marker parser maps canonical and legacy markers without guessing by citation order", () => {
  const segments = parseCitationMarkers(assistantAnswer, [limitedCitation, readyCitation]);
  const markers = segments.filter((segment) => segment.type === "citation");

  expect(markers.map((segment) => segment.marker)).toEqual(["S1", "S1", "S1", "S2"]);
  expect(markers.map((segment) => segment.citation.citation_marker)).toEqual([
    "S1",
    "S1",
    "S1",
    "S2"
  ]);
  expect(segments.map((segment) => segment.text).join("")).toBe(assistantAnswer);
});

test("marker parser leaves unknown, malformed, markdown-link and empty-citation text untouched", () => {
  const answer = "Unknown [S99], label [notes], year [2026], malformed [S-1], link [S1](url).";

  expect(parseCitationMarkers(answer, [readyCitation])).toEqual([
    { type: "text", text: answer }
  ]);
  expect(parseCitationMarkers("No sources [S1].", [])).toEqual([
    { type: "text", text: "No sources [S1]." }
  ]);
  expect(parseCitationMarkers("items[1] keeps an array index.", [readyCitation])).toEqual([
    { type: "text", text: "items[1] keeps an array index." }
  ]);
  expect(parseCitationMarkers("[1] numbered item", [readyCitation])).toEqual([
    { type: "text", text: "[1] numbered item" }
  ]);
});

test("personal team and conversation answer paths use the shared renderer", async () => {
  const root = process.cwd();
  const [askWorkspace, conversationPage, knowledgeBaseWorkspace] = await Promise.all([
    readFile(path.join(root, "components/qa/ask-workspace.tsx"), "utf-8"),
    readFile(path.join(root, "app/(dashboard)/conversations/[conversationId]/page.tsx"), "utf-8"),
    readFile(path.join(root, "components/knowledge-bases/knowledge-base-workspace.tsx"), "utf-8")
  ]);

  expect(askWorkspace).toContain("<CitationAwareAnswer");
  expect(conversationPage).toContain("<CitationAwareAnswer");
  expect(knowledgeBaseWorkspace).toContain("<AskWorkspace");
  expect(knowledgeBaseWorkspace).toContain('scope === "personal" ? askPersonal');
  expect(knowledgeBaseWorkspace).toContain("askTeam.mutateAsync");
});

test("personal knowledge base answer marker opens the shared drawer", async ({ page }) => {
  await mockPersonalWorkspace(page);
  await page.goto("/knowledge-bases/7");

  await page.locator("#ask-question").fill("How are citations mapped?");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  const marker = page.getByTestId("citation-marker-S1");
  await expect(marker).toBeVisible();
  await marker.click();
  await expect(page.getByTestId("citation-drawer")).toContainText(readyCitation.text);
});

test("conversation marker opens accessible drawer and supports every close path", async ({ page }) => {
  await mockConversationPage(page, "en");
  await page.goto("/conversations/42");

  const markers = page.getByTestId("citation-marker-S1");
  await expect(markers).toHaveCount(3);
  await expect(page.getByTestId("citation-marker-S2")).toHaveCount(1);
  await expect(page.getByTestId("citation-marker-S99")).toHaveCount(0);
  await expect(page.getByText("[S99]", { exact: false })).toBeVisible();
  await expect(page.getByText("[ordinary]", { exact: false })).toBeVisible();

  await markers.first().click();
  const drawer = page.getByTestId("citation-drawer");
  await expect(drawer).toBeVisible();
  await expect(drawer).toHaveAttribute("role", "dialog");
  await expect(drawer).toHaveAttribute("aria-modal", "true");
  await expect(drawer).toContainText("Citation 1");
  await expect(drawer).toContainText("retrieval-guide.txt");
  await expect(drawer).toContainText(readyCitation.text);
  await expect(drawer).toContainText("Citation contract");
  await expect(drawer).toContainText("Retrieval / Citation contract");
  await expect(page.getByTestId("citation-drawer-view-source")).toBeVisible();
  await expect(page.getByTestId("citation-drawer-close")).toBeFocused();
  expect(await page.evaluate(() => document.body.style.overflow)).toBe("hidden");

  await page.keyboard.press("Shift+Tab");
  await page.keyboard.press("Tab");
  await expect(page.getByTestId("citation-drawer-close")).toBeFocused();

  await drawer.getByText("Technical details").click();
  await expect(drawer).toContainText("Keyword + vector hybrid");
  await expect(drawer).toContainText("0.840");

  await page.getByTestId("citation-drawer-marker-S2").click();
  await expect(drawer).toContainText("Source details are limited for this citation.");
  await expect(drawer).toContainText(limitedCitation.text);
  await page.getByTestId("citation-drawer-marker-S1").click();
  await expect(drawer).toContainText(readyCitation.text);

  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();
  await expect(markers.first()).toBeFocused();
  expect(await page.evaluate(() => document.body.style.overflow)).toBe("");

  await markers.nth(1).click();
  await page.getByTestId("citation-drawer-close").click();
  await expect(markers.nth(1)).toBeFocused();

  await markers.nth(2).click();
  await page.getByTestId("citation-drawer-backdrop").click({ position: { x: 10, y: 10 } });
  await expect(drawer).toBeHidden();
  await expect(markers.nth(2)).toBeFocused();
});

test("limited citation omits unavailable source action", async ({ page }) => {
  await mockConversationPage(page, "en");
  await page.goto("/conversations/42");

  await page.getByTestId("citation-marker-S2").click();
  const drawer = page.getByTestId("citation-drawer");
  await expect(drawer).toContainText("Source details are limited for this citation.");
  await expect(drawer).toContainText(limitedCitation.text);
  await expect(page.getByTestId("citation-drawer-view-source")).toHaveCount(0);
});

test("mobile Chinese drawer fits viewport and keeps its header visible", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockConversationPage(page, "zh");
  await page.goto("/conversations/42");
  await page.getByTestId("citation-marker-S1").first().click();

  const drawer = page.getByTestId("citation-drawer");
  await expect(drawer).toContainText("引用 1");
  await expect(drawer).toContainText("引用原文");
  await expect(page.getByTestId("citation-drawer-close")).toBeVisible();
  await expect(drawer).toHaveCSS("transform", "none");
  const box = await drawer.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x).toBeLessThanOrEqual(1);
  expect(box!.width).toBeLessThanOrEqual(390);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

async function mockConversationPage(page: Page, locale: "en" | "zh") {
  await page.addInitScript(
    ({ selectedLocale }) => {
      window.localStorage.setItem("purelink_access_token", "citation-drawer-token");
      window.localStorage.setItem("purelink_locale", selectedLocale);
    },
    { selectedLocale: locale }
  );

  await page.route(API_PATTERN, async (route) => {
    const url = new URL(route.request().url());
    const pathName = url.pathname;
    const now = "2026-07-13T00:00:00Z";

    if (pathName.endsWith("/users/me")) {
      await fulfillJson(route, {
        id: 1,
        email: "citation@example.com",
        username: "citation_tester",
        is_active: true,
        created_at: now,
        updated_at: now
      });
      return;
    }
    if (pathName.endsWith("/conversations/42")) {
      await fulfillJson(route, {
        id: 42,
        knowledge_base_id: 7,
        title: "Citation UI test",
        scope: "personal",
        team_id: null,
        created_at: now,
        updated_at: now,
        messages: [
          { id: 1, role: "user", content: "Show cited details.", citations: [], created_at: now },
          {
            id: 2,
            role: "assistant",
            content: assistantAnswer,
            citations: [readyCitation, limitedCitation],
            created_at: now
          }
        ]
      });
      return;
    }
    if (pathName.endsWith("/conversations")) {
      await fulfillJson(route, [
        {
          id: 42,
          knowledge_base_id: 7,
          title: "Citation UI test",
          scope: "personal",
          team_id: null,
          created_at: now,
          updated_at: now
        }
      ]);
      return;
    }
    if (pathName.endsWith("/knowledge-bases/7/documents")) {
      await fulfillJson(route, [
        {
          id: 10,
          review_status: "not_required",
          processing_status: "indexed",
          latest_processing_job_status: "succeeded",
          latest_processing_job_error_code: null
        }
      ]);
      return;
    }
    if (pathName.endsWith("/knowledge-bases/7")) {
      await fulfillJson(route, {
        id: 7,
        name: "Citation Knowledge Base",
        description: null,
        scope: "personal",
        owner_id: 1,
        team_id: null,
        created_at: now,
        updated_at: now
      });
      return;
    }

    await route.fulfill({ status: 404, body: "Not mocked" });
  });
}

async function mockPersonalWorkspace(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("purelink_access_token", "citation-drawer-token");
    window.localStorage.setItem("purelink_locale", "en");
  });

  await page.route(API_PATTERN, async (route) => {
    const url = new URL(route.request().url());
    const pathName = url.pathname;
    const now = "2026-07-13T00:00:00Z";

    if (pathName.endsWith("/users/me")) {
      await fulfillJson(route, {
        id: 1,
        email: "citation@example.com",
        username: "citation_tester",
        is_active: true,
        created_at: now,
        updated_at: now
      });
      return;
    }
    if (
      pathName.endsWith("/knowledge-bases/7/ask") &&
      route.request().method() === "POST"
    ) {
      await fulfillJson(route, {
        conversation_id: 42,
        answer: "The answer uses final evidence [S1].",
        citations: [readyCitation],
        intent: "kb_fact_qa",
        retrieval_mode: "hybrid_text",
        requested_mode: "auto",
        selected_mode: "hybrid_text",
        router_reason: "technical query",
        used_reranker: false,
        trace_id: 12
      });
      return;
    }
    if (pathName.endsWith("/knowledge-bases/7/rag-health")) {
      await fulfillJson(route, {
        document_count: 1,
        document_status_counts: { indexed: 1 },
        index_status_counts: { vector: { ready: 1 } }
      });
      return;
    }
    if (pathName.endsWith("/knowledge-bases/7/documents")) {
      await fulfillJson(route, [
        {
          id: 10,
          original_filename: "retrieval-guide.txt",
          review_status: "not_required",
          processing_status: "indexed",
          latest_processing_job_status: "succeeded",
          latest_processing_job_error_code: null
        }
      ]);
      return;
    }
    if (pathName.endsWith("/knowledge-bases/7")) {
      await fulfillJson(route, {
        id: 7,
        name: "Citation Knowledge Base",
        description: null,
        scope: "personal",
        owner_id: 1,
        team_id: null,
        created_at: now,
        updated_at: now
      });
      return;
    }
    if (pathName.endsWith("/upload/constraints")) {
      await fulfillJson(route, {
        max_upload_size_mb: 25,
        max_upload_size_bytes: 26214400,
        allowed_extensions: ["txt"],
        allowed_mime_types: ["text/plain"]
      });
      return;
    }
    if (pathName.endsWith("/conversations")) {
      await fulfillJson(route, []);
      return;
    }

    await route.fulfill({ status: 404, body: "Not mocked" });
  });
}

async function fulfillJson(
  route: Parameters<Parameters<Page["route"]>[1]>[0],
  body: unknown
) {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body)
  });
}
