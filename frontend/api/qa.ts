import { apiClient } from "@/lib/api-client";
import { askResponseSchema } from "@/schemas/qa";
import type { AskResponse, RetrievalMode, RetrievalResponse } from "@/types";

export type RetrievalPayload = { query: string; top_k: number; mode?: RetrievalMode };

export function retrievePersonal(
  token: string,
  kbId: number,
  payload: RetrievalPayload
) {
  return apiClient.post<RetrievalResponse>(`/knowledge-bases/${kbId}/retrieve`, payload, token);
}

export async function askPersonal(
  token: string,
  kbId: number,
  payload: { question: string; top_k: number; conversation_id?: number | null; mode?: RetrievalMode }
) {
  const response = await apiClient.post<unknown>(`/knowledge-bases/${kbId}/ask`, payload, token);
  return askResponseSchema.parse(response) satisfies AskResponse;
}

export function retrieveTeam(
  token: string,
  teamId: number,
  kbId: number,
  payload: RetrievalPayload
) {
  return apiClient.post<RetrievalResponse>(
    `/teams/${teamId}/knowledge-bases/${kbId}/retrieve`,
    payload,
    token
  );
}

export async function askTeam(
  token: string,
  teamId: number,
  kbId: number,
  payload: { question: string; top_k: number; conversation_id?: number | null; mode?: RetrievalMode }
) {
  const response = await apiClient.post<unknown>(
    `/teams/${teamId}/knowledge-bases/${kbId}/ask`,
    payload,
    token
  );
  return askResponseSchema.parse(response) satisfies AskResponse;
}
