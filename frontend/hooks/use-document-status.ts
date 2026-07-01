"use client";

import { useQuery } from "@tanstack/react-query";

import * as documentApi from "@/api/documents";
import type { KnowledgeBaseScope } from "@/types";

export function useDocumentStatus({
  token,
  scope,
  knowledgeBaseId,
  documentId,
  teamId,
  enabled
}: {
  token: string | null;
  scope: KnowledgeBaseScope;
  knowledgeBaseId: number;
  documentId: number | null;
  teamId?: number;
  enabled: boolean;
}) {
  return useQuery({
    queryKey: ["document-status", scope, teamId ?? null, knowledgeBaseId, documentId],
    queryFn: () => {
      if (scope === "team") {
        return documentApi.getTeamDocumentStatus(
          token as string,
          teamId as number,
          knowledgeBaseId,
          documentId as number
        );
      }
      return documentApi.getPersonalDocumentStatus(
        token as string,
        knowledgeBaseId,
        documentId as number
      );
    },
    enabled:
      enabled &&
      Boolean(token) &&
      Number.isFinite(knowledgeBaseId) &&
      typeof documentId === "number" &&
      (scope === "personal" || Number.isFinite(teamId))
  });
}
