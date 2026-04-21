"use client";

import { useQuery } from "@tanstack/react-query";

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
