import { apiClient } from "@/lib/api-client";
import type { AskResponse, RetrievalResponse } from "@/types";

export function retrievePersonal(
  token: string,
  kbId: number,
  payload: { query: string; top_k: number }
) {
  return apiClient.post<RetrievalResponse>(`/knowledge-bases/${kbId}/retrieve`, payload, token);
}

export function askPersonal(
  token: string,
  kbId: number,
  payload: { question: string; top_k: number; conversation_id?: number | null }
) {
  return apiClient.post<AskResponse>(`/knowledge-bases/${kbId}/ask`, payload, token);
}

export function retrieveTeam(
  token: string,
  teamId: number,
  kbId: number,
  payload: { query: string; top_k: number }
) {
  return apiClient.post<RetrievalResponse>(
    `/teams/${teamId}/knowledge-bases/${kbId}/retrieve`,
    payload,
    token
  );
}

export function askTeam(
  token: string,
  teamId: number,
  kbId: number,
  payload: { question: string; top_k: number; conversation_id?: number | null }
) {
  return apiClient.post<AskResponse>(
    `/teams/${teamId}/knowledge-bases/${kbId}/ask`,
    payload,
    token
  );
}
