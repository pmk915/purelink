import { apiClient } from "@/lib/api-client";
import type {
  AppendConversationMessageResponse,
  Conversation,
  ConversationSummary
} from "@/types";

export function listConversations(token: string) {
  return apiClient.get<ConversationSummary[]>("/conversations", token);
}

export function getConversation(token: string, conversationId: number) {
  return apiClient.get<Conversation>(`/conversations/${conversationId}`, token);
}

export function appendConversationMessage(
  token: string,
  conversationId: number,
  payload: { content: string }
) {
  return apiClient.post<AppendConversationMessageResponse>(
    `/conversations/${conversationId}/messages`,
    payload,
    token
  );
}

export function deleteConversation(token: string, conversationId: number) {
  return apiClient.delete<void>(`/conversations/${conversationId}`, token);
}
