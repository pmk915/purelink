import { apiClient } from "@/lib/api-client";
import type { KnowledgeBase, KnowledgeBaseRagHealth } from "@/types";

export function listPersonalKnowledgeBases(token: string) {
  return apiClient.get<KnowledgeBase[]>("/knowledge-bases", token);
}

export function createPersonalKnowledgeBase(
  token: string,
  payload: { name: string; description?: string | null }
) {
  return apiClient.post<KnowledgeBase>("/knowledge-bases", payload, token);
}

export function getPersonalKnowledgeBase(token: string, kbId: number) {
  return apiClient.get<KnowledgeBase>(`/knowledge-bases/${kbId}`, token);
}

export function updatePersonalKnowledgeBase(
  token: string,
  kbId: number,
  payload: { name?: string; description?: string | null }
) {
  return apiClient.patch<KnowledgeBase>(`/knowledge-bases/${kbId}`, payload, token);
}

export function deletePersonalKnowledgeBase(token: string, kbId: number) {
  return apiClient.delete<void>(`/knowledge-bases/${kbId}`, token);
}

export function getPersonalKnowledgeBaseRagHealth(token: string, kbId: number) {
  return apiClient.get<KnowledgeBaseRagHealth>(`/knowledge-bases/${kbId}/rag-health`, token);
}
