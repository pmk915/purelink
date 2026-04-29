"use client";

import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import * as documentApi from "@/api/documents";
import { DocumentCard } from "@/components/documents/document-card";
import { DocumentUploadCard } from "@/components/documents/document-upload-card";
import { AskWorkspace, type QaAvailability } from "@/components/qa/ask-workspace";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/hooks/use-auth";
import { useI18n } from "@/hooks/use-i18n";
import {
  usePersonalDocuments,
  useTeamDocuments,
  useUploadPersonalDocument,
  useUploadTeamDocument
} from "@/hooks/use-documents";
import {
  usePersonalKnowledgeBase,
  useTeamKnowledgeBase
} from "@/hooks/use-knowledge-bases";
import { useTeam } from "@/hooks/use-teams";
import { useAskPersonal, useAskTeam } from "@/hooks/use-qa";
import type { Document, KnowledgeBaseScope } from "@/types";

function supportsDocumentPreparation(filename: string) {
  const normalized = filename.toLowerCase();
  return (
    normalized.endsWith(".txt") ||
    normalized.endsWith(".md") ||
    normalized.endsWith(".pdf")
  );
}

type FeedbackState = {
  tone: "info" | "success" | "error";
  message: string;
};

function getFeedbackClassName(tone: FeedbackState["tone"]) {
  if (tone === "success") {
    return "rounded-2xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700";
  }

  if (tone === "error") {
    return "rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700";
  }

  return "rounded-2xl bg-sky-50 px-4 py-3 text-sm text-sky-700";
}

function isDocumentQueryable(document: Document) {
  return (
    document.review_status !== "pending_review" &&
    document.review_status !== "rejected" &&
    (document.processing_status === "ready" ||
      document.processing_status === "indexed")
  );
}

function isDocumentPreparing(document: Document) {
  if (
    document.review_status === "pending_review" ||
    document.review_status === "rejected"
  ) {
    return false;
  }

  return (
    document.processing_status === "uploaded" ||
    document.processing_status === "processing" ||
    document.processing_status === "parsed" ||
    document.latest_processing_job_status === "queued" ||
    document.latest_processing_job_status === "processing" ||
    document.latest_processing_job_status === "retrying"
  );
}

function getQaAvailability(documents: Document[]): QaAvailability {
  if (documents.length === 0) {
    return "empty";
  }

  if (documents.some(isDocumentQueryable)) {
    return "ready";
  }

  if (documents.some((document) => document.review_status === "pending_review")) {
    return "waiting_review";
  }

  if (documents.some(isDocumentPreparing)) {
    return "preparing";
  }

  return "unavailable";
}

export function KnowledgeBaseWorkspace({
  scope,
  knowledgeBaseId,
  teamId
}: {
  scope: KnowledgeBaseScope;
  knowledgeBaseId: number;
  teamId?: number;
}) {
  const { accessToken } = useAuth();
  const { messages } = useI18n();
  const queryClient = useQueryClient();
  const [processingDocumentIds, setProcessingDocumentIds] = useState<number[]>([]);
  const [feedback, setFeedback] = useState<FeedbackState | null>(null);

  const personalKbQuery = usePersonalKnowledgeBase(accessToken, knowledgeBaseId);
  const teamKbQuery = useTeamKnowledgeBase(accessToken, teamId ?? Number.NaN, knowledgeBaseId);
  const teamQuery = useTeam(scope === "team" ? accessToken : null, teamId ?? Number.NaN);
  const personalDocumentsQuery = usePersonalDocuments(accessToken, knowledgeBaseId);
  const teamDocumentsQuery = useTeamDocuments(accessToken, teamId ?? Number.NaN, knowledgeBaseId);
  const uploadPersonal = useUploadPersonalDocument(accessToken, knowledgeBaseId);
  const uploadTeam = useUploadTeamDocument(accessToken, teamId ?? Number.NaN, knowledgeBaseId);
  const askPersonal = useAskPersonal(accessToken, knowledgeBaseId);
  const askTeam = useAskTeam(accessToken, teamId ?? Number.NaN, knowledgeBaseId);

  const knowledgeBase = scope === "personal" ? personalKbQuery.data : teamKbQuery.data;
  const documents =
    scope === "personal" ? personalDocumentsQuery.data ?? [] : teamDocumentsQuery.data ?? [];
  const isTeamAdmin = scope === "team" && teamQuery.data?.my_role === "admin";

  const isLoading = useMemo(
    () =>
      personalKbQuery.isLoading ||
      teamKbQuery.isLoading ||
      personalDocumentsQuery.isLoading ||
      teamDocumentsQuery.isLoading ||
      teamQuery.isLoading,
    [
      personalDocumentsQuery.isLoading,
      personalKbQuery.isLoading,
      teamDocumentsQuery.isLoading,
      teamQuery.isLoading,
      teamKbQuery.isLoading
    ]
  );

  const qaAvailability = getQaAvailability(documents);

  const invalidateDocuments = async () => {
    if (scope === "personal") {
      await queryClient.invalidateQueries({
        queryKey: ["documents", "personal", knowledgeBaseId]
      });
      return;
    }

    await queryClient.invalidateQueries({
      queryKey: ["documents", "team", teamId, knowledgeBaseId]
    });
  };

  const runProcessingPipeline = async (
    document: Document,
    options?: { triggeredByUpload?: boolean }
  ) => {
    if (!accessToken) {
      setFeedback({
        tone: "error",
        message: messages.documents.processingFailed
      });
      return;
    }

    if (!supportsDocumentPreparation(document.original_filename)) {
      setFeedback({
        tone: "error",
        message: messages.documents.unsupportedFileType
      });
      return;
    }

    setProcessingDocumentIds((current) =>
      current.includes(document.id) ? current : [...current, document.id]
    );
    setFeedback({
      tone: "info",
      message: options?.triggeredByUpload
        ? messages.documents.uploadProcessingStarted(document.original_filename)
        : messages.documents.statusProcessingHint
    });

    try {
      if (scope === "personal") {
        await documentApi.processPersonalDocument(accessToken, knowledgeBaseId, document.id);
      } else {
        if (!teamId) {
          throw new Error(messages.documents.processingFailed);
        }

        await documentApi.processTeamDocument(
          accessToken,
          teamId,
          knowledgeBaseId,
          document.id
        );
      }

      await invalidateDocuments();
      setFeedback({
        tone: "info",
        message: messages.documents.processingSubmitted(document.original_filename)
      });
    } catch (error) {
      console.error("document processing failed", {
        error,
        documentId: document.id,
        knowledgeBaseId,
        scope,
        teamId: teamId ?? null
      });

      await invalidateDocuments();
      setFeedback({
        tone: "error",
        message: messages.documents.processingFailedHelp
      });
    } finally {
      setProcessingDocumentIds((current) =>
        current.filter((documentId) => documentId !== document.id)
      );
    }
  };

  if (isLoading) {
    return (
      <div className="rounded-3xl border border-border/70 bg-white/80 px-6 py-10 text-sm text-muted-foreground shadow-card">
        {messages.common.loadingWorkspace}
      </div>
    );
  }

  if (!knowledgeBase) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{messages.knowledgeBases.notFoundTitle}</CardTitle>
          <CardDescription>{messages.knowledgeBases.notFoundDescription}</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <CardTitle className="text-2xl">{knowledgeBase.name}</CardTitle>
              <CardDescription className="mt-3 max-w-3xl text-base leading-7">
                {knowledgeBase.description ?? messages.common.noDescription}
              </CardDescription>
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge variant={scope === "team" ? "secondary" : "default"}>
                {scope === "team" ? messages.common.team : messages.common.personal}
              </Badge>
              {teamId ? <Badge variant="outline">{messages.common.teamId(teamId)}</Badge> : null}
            </div>
          </div>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-4 text-sm text-muted-foreground">
          <span>{messages.common.knowledgeBaseId(knowledgeBase.id)}</span>
          <span>
            {messages.common.updatedAt} {new Date(knowledgeBase.updated_at).toLocaleString()}
          </span>
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
        <div className="space-y-6">
          <DocumentUploadCard
            title={messages.knowledgeBases.uploadTitle}
            description={
              scope === "personal"
                ? messages.knowledgeBases.uploadDescriptionPersonal
                : messages.knowledgeBases.uploadDescriptionTeam
            }
            onUpload={async (file) => {
              if (scope === "personal") {
                const uploadedDocument = await uploadPersonal.mutateAsync(file);
                setFeedback({
                  tone: "success",
                  message: messages.documents.uploadProcessingStarted(
                    uploadedDocument.original_filename
                  )
                });
                return;
              }

              const uploadedDocument = await uploadTeam.mutateAsync(file);
              if (isTeamAdmin) {
                setFeedback({
                  tone: "success",
                  message: messages.documents.uploadProcessingStarted(
                    uploadedDocument.original_filename
                  )
                });
                return;
              }

              setFeedback({
                tone: "success",
                message: messages.documents.uploadSubmittedForReview(
                  uploadedDocument.original_filename
                )
              });
            }}
            isUploading={uploadPersonal.isPending || uploadTeam.isPending}
          />

          {feedback ? (
            <div className={getFeedbackClassName(feedback.tone)}>{feedback.message}</div>
          ) : null}
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>{messages.knowledgeBases.documentsTitle}</CardTitle>
              <CardDescription>{messages.knowledgeBases.documentsDescription}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {documents.length === 0 ? (
                <div className="rounded-2xl bg-secondary/60 p-4 text-sm text-muted-foreground">
                  {messages.knowledgeBases.noDocuments}
                </div>
              ) : null}

              {documents.map((document) => (
                <DocumentCard
                  key={document.id}
                  document={document}
                  isProcessing={processingDocumentIds.includes(document.id)}
                  onProcess={
                    document.processing_status === "failed"
                      ? async () => {
                          await runProcessingPipeline(document);
                        }
                      : null
                  }
                />
              ))}
            </CardContent>
          </Card>

          <AskWorkspace
            availability={qaAvailability}
            onAsk={(values) =>
              scope === "personal" ? askPersonal.mutateAsync(values) : askTeam.mutateAsync(values)
            }
          />
        </div>
      </div>
    </div>
  );
}
