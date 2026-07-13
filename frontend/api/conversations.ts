import { apiClient } from "@/lib/api-client";
import {
  appendConversationMessageResponseSchema,
  conversationSchema
} from "@/schemas/conversations";
import type {
  AppendConversationMessageResponse,
  Conversation,
  ConversationSummary
} from "@/types";

export function listConversations(token: string) {
  return apiClient.get<ConversationSummary[]>("/conversations", token);
}

export async function getConversation(token: string, conversationId: number) {
  const response = await apiClient.get<unknown>(`/conversations/${conversationId}`, token);
  return conversationSchema.parse(response) satisfies Conversation;
}

export async function appendConversationMessage(
  token: string,
  conversationId: number,
  payload: { content: string }
) {
  const response = await apiClient.post<unknown>(
    `/conversations/${conversationId}/messages`,
    payload,
    token
  );
  return appendConversationMessageResponseSchema.parse(
    response
  ) satisfies AppendConversationMessageResponse;
}

export function deleteConversation(token: string, conversationId: number) {
  return apiClient.delete<void>(`/conversations/${conversationId}`, token);
}
