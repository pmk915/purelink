import { apiClient } from "@/lib/api-client";
import type { Conversation, ConversationSummary } from "@/types";

export function listConversations(token: string) {
  return apiClient.get<ConversationSummary[]>("/conversations", token);
}

export function getConversation(token: string, conversationId: number) {
  return apiClient.get<Conversation>(`/conversations/${conversationId}`, token);
}
