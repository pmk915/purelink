import { apiClient } from "@/lib/api-client";
import type {
  KnowledgeBase,
  KnowledgeBaseRagHealth,
  KnowledgeGraphEntityDetail,
  KnowledgeGraphEntityList,
  Team,
  TeamInvite,
  TeamMember
} from "@/types";

export function listTeams(token: string) {
  return apiClient.get<Team[]>("/teams", token);
}

export function createTeam(
  token: string,
  payload: { name: string; description?: string | null }
) {
  return apiClient.post<Team>("/teams", payload, token);
}

export function getTeam(token: string, teamId: number) {
  return apiClient.get<Team>(`/teams/${teamId}`, token);
}

export function joinTeamByCode(token: string, payload: { code: string }) {
  return apiClient.post<Team>("/team-invites/join", payload, token);
}

export function listTeamMembers(token: string, teamId: number) {
  return apiClient.get<TeamMember[]>(`/teams/${teamId}/members`, token);
}

export function listTeamInvites(token: string, teamId: number) {
  return apiClient.get<TeamInvite[]>(`/teams/${teamId}/invites`, token);
}

export function createTeamInvite(
  token: string,
  teamId: number,
  payload: { expires_in_days: number }
) {
  return apiClient.post<TeamInvite>(`/teams/${teamId}/invites`, payload, token);
}

export function listTeamKnowledgeBases(token: string, teamId: number) {
  return apiClient.get<KnowledgeBase[]>(`/teams/${teamId}/knowledge-bases`, token);
}

export function createTeamKnowledgeBase(
  token: string,
  teamId: number,
  payload: { name: string; description?: string | null }
) {
  return apiClient.post<KnowledgeBase>(`/teams/${teamId}/knowledge-bases`, payload, token);
}

export function getTeamKnowledgeBase(token: string, teamId: number, kbId: number) {
  return apiClient.get<KnowledgeBase>(`/teams/${teamId}/knowledge-bases/${kbId}`, token);
}

export function deleteTeamKnowledgeBase(token: string, teamId: number, kbId: number) {
  return apiClient.delete<void>(`/teams/${teamId}/knowledge-bases/${kbId}`, token);
}

export function getTeamKnowledgeBaseRagHealth(token: string, teamId: number, kbId: number) {
  return apiClient.get<KnowledgeBaseRagHealth>(
    `/teams/${teamId}/knowledge-bases/${kbId}/rag-health`,
    token
  );
}

export function listTeamKnowledgeGraphEntities(
  token: string,
  teamId: number,
  kbId: number,
  query?: string
) {
  const search = query ? `?q=${encodeURIComponent(query)}` : "";
  return apiClient.get<KnowledgeGraphEntityList>(
    `/teams/${teamId}/knowledge-bases/${kbId}/graph/entities${search}`,
    token
  );
}

export function getTeamKnowledgeGraphEntity(
  token: string,
  teamId: number,
  kbId: number,
  entityId: number
) {
  return apiClient.get<KnowledgeGraphEntityDetail>(
    `/teams/${teamId}/knowledge-bases/${kbId}/graph/entities/${entityId}`,
    token
  );
}
