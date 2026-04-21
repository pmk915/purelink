"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import * as teamsApi from "@/api/teams";

export function useTeams(token: string | null) {
  return useQuery({
    queryKey: ["teams"],
    queryFn: () => teamsApi.listTeams(token as string),
    enabled: Boolean(token)
  });
}

export function useTeam(token: string | null, teamId: number) {
  return useQuery({
    queryKey: ["teams", teamId],
    queryFn: () => teamsApi.getTeam(token as string, teamId),
    enabled: Boolean(token) && Number.isFinite(teamId)
  });
}

export function useTeamMembers(token: string | null, teamId: number) {
  return useQuery({
    queryKey: ["teams", teamId, "members"],
    queryFn: () => teamsApi.listTeamMembers(token as string, teamId),
    enabled: Boolean(token) && Number.isFinite(teamId)
  });
}

export function useTeamInvites(token: string | null, teamId: number) {
  return useQuery({
    queryKey: ["teams", teamId, "invites"],
    queryFn: () => teamsApi.listTeamInvites(token as string, teamId),
    enabled: Boolean(token) && Number.isFinite(teamId)
  });
}

export function useCreateTeam(token: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { name: string; description?: string | null }) =>
      teamsApi.createTeam(token as string, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["teams"] });
    }
  });
}

export function useJoinTeam(token: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { code: string }) => teamsApi.joinTeamByCode(token as string, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["teams"] });
    }
  });
}

export function useCreateTeamInvite(token: string | null, teamId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { expires_in_days: number }) =>
      teamsApi.createTeamInvite(token as string, teamId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["teams", teamId, "invites"] });
    }
  });
}
