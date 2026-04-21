"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import * as documentApi from "@/api/documents";
import type { DocumentTaskType } from "@/types";

export function usePersonalDocuments(token: string | null, kbId: number) {
  return useQuery({
    queryKey: ["documents", "personal", kbId],
    queryFn: () => documentApi.listPersonalDocuments(token as string, kbId),
    enabled: Boolean(token) && Number.isFinite(kbId)
  });
}

export function useTeamDocuments(token: string | null, teamId: number, kbId: number) {
  return useQuery({
    queryKey: ["documents", "team", teamId, kbId],
    queryFn: () => documentApi.listTeamDocuments(token as string, teamId, kbId),
    enabled: Boolean(token) && Number.isFinite(teamId) && Number.isFinite(kbId)
  });
}

export function useUploadPersonalDocument(token: string | null, kbId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => documentApi.uploadPersonalDocument(token as string, kbId, file),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["documents", "personal", kbId] });
    }
  });
}

export function useUploadTeamDocument(token: string | null, teamId: number, kbId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) =>
      documentApi.uploadTeamDocument(token as string, teamId, kbId, file),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["documents", "team", teamId, kbId] });
      await queryClient.invalidateQueries({ queryKey: ["team-review-tasks", teamId] });
    }
  });
}

export function useTeamReviewTasks(token: string | null, teamId: number) {
  return useQuery({
    queryKey: ["team-review-tasks", teamId],
    queryFn: () => documentApi.listTeamReviewTasks(token as string, teamId),
    enabled: Boolean(token) && Number.isFinite(teamId)
  });
}

export function useApproveTeamDocument(token: string | null, teamId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (documentId: number) =>
      documentApi.approveTeamDocument(token as string, teamId, documentId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["team-review-tasks", teamId] });
    }
  });
}

export function useRejectTeamDocument(token: string | null, teamId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { documentId: number; review_comment: string }) =>
      documentApi.rejectTeamDocument(token as string, teamId, payload.documentId, {
        review_comment: payload.review_comment
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["team-review-tasks", teamId] });
    }
  });
}

export function useCreatePersonalTask(token: string | null, kbId: number) {
  return useMutation({
    mutationFn: (payload: { documentId: number; taskType: DocumentTaskType }) =>
      documentApi.createPersonalTask(token as string, kbId, payload.documentId, payload.taskType)
  });
}

export function useCreateTeamTask(token: string | null, teamId: number, kbId: number) {
  return useMutation({
    mutationFn: (payload: { documentId: number; taskType: DocumentTaskType }) =>
      documentApi.createTeamTask(
        token as string,
        teamId,
        kbId,
        payload.documentId,
        payload.taskType
      )
  });
}

export function useDocumentTask(token: string | null, taskId: number | null) {
  return useQuery({
    queryKey: ["document-task", taskId],
    queryFn: () => documentApi.getDocumentTask(token as string, taskId as number),
    enabled: Boolean(token) && typeof taskId === "number",
    refetchInterval: (query) => {
      const task = query.state.data;
      if (!task) {
        return false;
      }
      return task.status === "pending" || task.status === "processing" ? 2500 : false;
    }
  });
}
