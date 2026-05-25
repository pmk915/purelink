"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import * as knowledgeBaseApi from "@/api/knowledge-bases";
import * as teamsApi from "@/api/teams";

export function usePersonalKnowledgeBases(token: string | null) {
  return useQuery({
    queryKey: ["knowledge-bases", "personal"],
    queryFn: () => knowledgeBaseApi.listPersonalKnowledgeBases(token as string),
    enabled: Boolean(token)
  });
}

export function usePersonalKnowledgeBase(token: string | null, kbId: number) {
  return useQuery({
    queryKey: ["knowledge-bases", "personal", kbId],
    queryFn: () => knowledgeBaseApi.getPersonalKnowledgeBase(token as string, kbId),
    enabled: Boolean(token) && Number.isFinite(kbId)
  });
}

export function useCreatePersonalKnowledgeBase(token: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { name: string; description?: string | null }) =>
      knowledgeBaseApi.createPersonalKnowledgeBase(token as string, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["knowledge-bases", "personal"] });
    }
  });
}

export function useDeletePersonalKnowledgeBase(token: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (kbId: number) =>
      knowledgeBaseApi.deletePersonalKnowledgeBase(token as string, kbId),
    onSuccess: async (_, kbId) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["knowledge-bases", "personal"] }),
        queryClient.removeQueries({ queryKey: ["knowledge-bases", "personal", kbId] }),
        queryClient.removeQueries({ queryKey: ["knowledge-base-health", "personal", kbId] })
      ]);
    }
  });
}

export function usePersonalKnowledgeBaseRagHealth(token: string | null, kbId: number) {
  return useQuery({
    queryKey: ["knowledge-base-health", "personal", kbId],
    queryFn: () => knowledgeBaseApi.getPersonalKnowledgeBaseRagHealth(token as string, kbId),
    enabled: Boolean(token) && Number.isFinite(kbId)
  });
}

export function useTeamsKnowledgeBases(token: string | null, teamId: number) {
  return useQuery({
    queryKey: ["knowledge-bases", "team", teamId],
    queryFn: () => teamsApi.listTeamKnowledgeBases(token as string, teamId),
    enabled: Boolean(token) && Number.isFinite(teamId)
  });
}

export function useTeamKnowledgeBase(token: string | null, teamId: number, kbId: number) {
  return useQuery({
    queryKey: ["knowledge-bases", "team", teamId, kbId],
    queryFn: () => teamsApi.getTeamKnowledgeBase(token as string, teamId, kbId),
    enabled: Boolean(token) && Number.isFinite(teamId) && Number.isFinite(kbId)
  });
}

export function useCreateTeamKnowledgeBase(token: string | null, teamId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { name: string; description?: string | null }) =>
      teamsApi.createTeamKnowledgeBase(token as string, teamId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["knowledge-bases", "team", teamId] });
    }
  });
}

export function useDeleteTeamKnowledgeBase(token: string | null, teamId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (kbId: number) =>
      teamsApi.deleteTeamKnowledgeBase(token as string, teamId, kbId),
    onSuccess: async (_, kbId) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["knowledge-bases", "team", teamId] }),
        queryClient.removeQueries({ queryKey: ["knowledge-bases", "team", teamId, kbId] }),
        queryClient.removeQueries({ queryKey: ["knowledge-base-health", "team", teamId, kbId] })
      ]);
    }
  });
}

export function useTeamKnowledgeBaseRagHealth(
  token: string | null,
  teamId: number,
  kbId: number
) {
  return useQuery({
    queryKey: ["knowledge-base-health", "team", teamId, kbId],
    queryFn: () => teamsApi.getTeamKnowledgeBaseRagHealth(token as string, teamId, kbId),
    enabled: Boolean(token) && Number.isFinite(teamId) && Number.isFinite(kbId)
  });
}
