import { apiClient } from "@/lib/api-client";
import type {
  KnowledgeBase,
  KnowledgeBaseRagHealth,
  KnowledgeGraphEntityDetail,
  KnowledgeGraphEntityList,
  KnowledgeGraphExport,
  KnowledgeGraphExportParams
} from "@/types";

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

export function listPersonalKnowledgeGraphEntities(
  token: string,
  kbId: number,
  query?: string
) {
  const search = query ? `?q=${encodeURIComponent(query)}` : "";
  return apiClient.get<KnowledgeGraphEntityList>(
    `/knowledge-bases/${kbId}/graph/entities${search}`,
    token
  );
}

export function getPersonalKnowledgeGraphEntity(token: string, kbId: number, entityId: number) {
  return apiClient.get<KnowledgeGraphEntityDetail>(
    `/knowledge-bases/${kbId}/graph/entities/${entityId}`,
    token
  );
}

export function exportPersonalKnowledgeGraph(
  token: string,
  kbId: number,
  params: KnowledgeGraphExportParams = {}
) {
  const search = buildGraphExportSearch(params);
  return apiClient.get<KnowledgeGraphExport>(
    `/knowledge-bases/${kbId}/graph/export${search}`,
    token
  );
}

function buildGraphExportSearch(params: KnowledgeGraphExportParams) {
  const searchParams = new URLSearchParams();
  if (params.q?.trim()) {
    searchParams.set("q", params.q.trim());
  }
  if (params.relation_type?.trim()) {
    searchParams.set("relation_type", params.relation_type.trim());
  }
  if (typeof params.entity_id === "number") {
    searchParams.set("entity_id", String(params.entity_id));
  }
  if (typeof params.limit_entities === "number") {
    searchParams.set("limit_entities", String(params.limit_entities));
  }
  if (typeof params.limit_relations === "number") {
    searchParams.set("limit_relations", String(params.limit_relations));
  }
  if (typeof params.limit_sources_per_relation === "number") {
    searchParams.set("limit_sources_per_relation", String(params.limit_sources_per_relation));
  }
  const search = searchParams.toString();
  return search ? `?${search}` : "";
}
