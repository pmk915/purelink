"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import * as conversationApi from "@/api/conversations";

export function useConversations(token: string | null) {
  return useQuery({
    queryKey: ["conversations"],
    queryFn: () => conversationApi.listConversations(token as string),
    enabled: Boolean(token)
  });
}

export function useConversation(token: string | null, conversationId: number) {
  return useQuery({
    queryKey: ["conversations", conversationId],
    queryFn: () => conversationApi.getConversation(token as string, conversationId),
    enabled: Boolean(token) && Number.isFinite(conversationId)
  });
}

export function useAppendConversationMessage(token: string | null, conversationId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { content: string }) =>
      conversationApi.appendConversationMessage(token as string, conversationId, payload),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["conversations"] }),
        queryClient.invalidateQueries({ queryKey: ["conversations", conversationId] })
      ]);
    }
  });
}

export function useDeleteConversation(token: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (conversationId: number) =>
      conversationApi.deleteConversation(token as string, conversationId),
    onSuccess: async (_, conversationId) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["conversations"] }),
        queryClient.removeQueries({ queryKey: ["conversations", conversationId] })
      ]);
    }
  });
}
