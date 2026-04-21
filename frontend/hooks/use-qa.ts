"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import * as qaApi from "@/api/qa";

export function useRetrievePersonal(token: string | null, kbId: number) {
  return useMutation({
    mutationFn: (payload: { query: string; top_k: number }) =>
      qaApi.retrievePersonal(token as string, kbId, payload)
  });
}

export function useAskPersonal(token: string | null, kbId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      question: string;
      top_k: number;
      conversation_id?: number | null;
    }) => qaApi.askPersonal(token as string, kbId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["conversations"] });
    }
  });
}

export function useRetrieveTeam(token: string | null, teamId: number, kbId: number) {
  return useMutation({
    mutationFn: (payload: { query: string; top_k: number }) =>
      qaApi.retrieveTeam(token as string, teamId, kbId, payload)
  });
}

export function useAskTeam(token: string | null, teamId: number, kbId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      question: string;
      top_k: number;
      conversation_id?: number | null;
    }) => qaApi.askTeam(token as string, teamId, kbId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["conversations"] });
    }
  });
}
