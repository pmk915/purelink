"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import * as documentApi from "@/api/documents";
import { DocumentListItem } from "@/components/documents/document-list-item";
import { DocumentUploadCard } from "@/components/documents/document-upload-card";
import { AskWorkspace, type QaAvailability } from "@/components/qa/ask-workspace";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useAuth } from "@/hooks/use-auth";
import { useConversations } from "@/hooks/use-conversations";
import { useI18n } from "@/hooks/use-i18n";
import {
  useDeletePersonalDocument,
  useDeleteTeamDocument,
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
import { formatDate } from "@/lib/utils";
import type { Document, KnowledgeBaseScope } from "@/types";

function supportsDocumentPreparation(filename: string) {
  const normalized = filename.toLowerCase();
  return (
    normalized.endsWith(".txt") ||
    normalized.endsWith(".md") ||
    normalized.endsWith(".docx") ||
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
    document.processing_status === "indexed"
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

type WorkspaceTab = "qa" | "documents";

export function KnowledgeBaseWorkspace({
  scope,
  knowledgeBaseId,
  teamId
}: {
  scope: KnowledgeBaseScope;
  knowledgeBaseId: number;
  teamId?: number;
}) {
  const { accessToken, currentUser } = useAuth();
  const { messages } = useI18n();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("qa");
  const [processingDocumentIds, setProcessingDocumentIds] = useState<number[]>([]);
  const [feedback, setFeedback] = useState<FeedbackState | null>(null);
  const [pendingDeleteDocument, setPendingDeleteDocument] = useState<Document | null>(null);

  const personalKbQuery = usePersonalKnowledgeBase(accessToken, knowledgeBaseId);
  const teamKbQuery = useTeamKnowledgeBase(accessToken, teamId ?? Number.NaN, knowledgeBaseId);
  const teamQuery = useTeam(scope === "team" ? accessToken : null, teamId ?? Number.NaN);
  const personalDocumentsQuery = usePersonalDocuments(accessToken, knowledgeBaseId);
  const teamDocumentsQuery = useTeamDocuments(accessToken, teamId ?? Number.NaN, knowledgeBaseId);
  const conversationsQuery = useConversations(accessToken);
  const uploadPersonal = useUploadPersonalDocument(accessToken, knowledgeBaseId);
  const uploadTeam = useUploadTeamDocument(accessToken, teamId ?? Number.NaN, knowledgeBaseId);
  const deletePersonalDocument = useDeletePersonalDocument(accessToken, knowledgeBaseId);
  const deleteTeamDocument = useDeleteTeamDocument(
    accessToken,
    teamId ?? Number.NaN,
    knowledgeBaseId
  );
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
  const totalDocuments = documents.length;
  const askableDocuments = documents.filter(isDocumentQueryable).length;
  const failedDocuments = documents.filter((document) => document.processing_status === "failed").length;
  const preparingDocuments = documents.filter(isDocumentPreparing).length;
  const recentConversations = useMemo(
    () =>
      (conversationsQuery.data ?? [])
        .filter(
          (conversation) =>
            conversation.knowledge_base_id === knowledgeBaseId &&
            conversation.scope === scope &&
            conversation.team_id === (teamId ?? null)
        )
        .slice(0, 4),
    [conversationsQuery.data, knowledgeBaseId, scope, teamId]
  );

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

  const deleteDisabledReason =
    scope === "team" ? messages.documents.onlyTeamAdminsOrOwnersCanDelete : null;

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

  const tabButtonClassName = (tab: WorkspaceTab) =>
    tab === activeTab ? "default" : "ghost";

  return (
    <div className="space-y-6">
      <ConfirmDialog
        open={pendingDeleteDocument !== null}
        title={messages.documents.deleteDialogTitle}
        description={
          pendingDeleteDocument
            ? messages.documents.deleteDialogDescription(pendingDeleteDocument.original_filename)
            : undefined
        }
        cancelLabel={messages.common.cancel}
        confirmLabel={
          deletePersonalDocument.isPending || deleteTeamDocument.isPending
            ? messages.common.deleting
            : messages.common.delete
        }
        destructive
        loading={deletePersonalDocument.isPending || deleteTeamDocument.isPending}
        onCancel={() => setPendingDeleteDocument(null)}
        onConfirm={async () => {
          if (!pendingDeleteDocument) {
            return;
          }

          try {
            if (scope === "personal") {
              await deletePersonalDocument.mutateAsync(pendingDeleteDocument.id);
            } else if (teamId) {
              await deleteTeamDocument.mutateAsync(pendingDeleteDocument.id);
            }

            setFeedback({
              tone: "success",
              message: messages.documents.deleteSucceeded(pendingDeleteDocument.original_filename)
            });
            setPendingDeleteDocument(null);
          } catch (error) {
            console.error("document delete failed", {
              error,
              documentId: pendingDeleteDocument.id,
              knowledgeBaseId,
              scope,
              teamId: teamId ?? null
            });
            setFeedback({
              tone: "error",
              message: messages.documents.deleteFailed
            });
          }
        }}
      />

      <Card className="border-border/70 shadow-card">
        <CardHeader className="space-y-4">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={scope === "team" ? "secondary" : "default"}>
                  {scope === "team" ? messages.common.team : messages.common.personal}
                </Badge>
                {teamId ? <Badge variant="outline">{messages.common.teamId(teamId)}</Badge> : null}
                <Badge variant={askableDocuments > 0 ? "default" : "outline"}>
                  {askableDocuments > 0 ? messages.documents.statusAvailable : messages.documents.statusProcessing}
                </Badge>
              </div>
              <div>
                <CardTitle className="text-2xl">{knowledgeBase.name}</CardTitle>
                <CardDescription className="mt-2 max-w-3xl text-sm leading-7">
                  {knowledgeBase.description ?? messages.common.noDescription}
                </CardDescription>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 text-sm text-muted-foreground sm:grid-cols-4">
              <div className="rounded-2xl bg-secondary/60 px-4 py-3">
                <p className="text-xs uppercase tracking-[0.18em]">{messages.knowledgeBases.documentsTab}</p>
                <p className="mt-2 text-lg font-semibold text-foreground">{totalDocuments}</p>
              </div>
              <div className="rounded-2xl bg-secondary/60 px-4 py-3">
                <p className="text-xs uppercase tracking-[0.18em]">{messages.knowledgeBases.askTab}</p>
                <p className="mt-2 text-lg font-semibold text-foreground">{askableDocuments}</p>
              </div>
              <div className="rounded-2xl bg-secondary/60 px-4 py-3">
                <p className="text-xs uppercase tracking-[0.18em]">{messages.common.processing}</p>
                <p className="mt-2 text-lg font-semibold text-foreground">{preparingDocuments}</p>
              </div>
              <div className="rounded-2xl bg-secondary/60 px-4 py-3">
                <p className="text-xs uppercase tracking-[0.18em]">{messages.documents.processingFailed}</p>
                <p className="mt-2 text-lg font-semibold text-foreground">{failedDocuments}</p>
              </div>
            </div>
          </div>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
          <div className="flex flex-wrap gap-4">
            <span>{messages.common.knowledgeBaseId(knowledgeBase.id)}</span>
            <span>
              {messages.common.updatedAt} {formatDate(knowledgeBase.updated_at)}
            </span>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              variant={tabButtonClassName("qa")}
              size="sm"
              onClick={() => setActiveTab("qa")}
            >
              {messages.knowledgeBases.askTab}
            </Button>
            <Button
              variant={tabButtonClassName("documents")}
              size="sm"
              onClick={() => setActiveTab("documents")}
            >
              {messages.knowledgeBases.documentsTab}
            </Button>
          </div>
        </CardContent>
      </Card>

      {activeTab === "qa" ? (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1.55fr)_340px]">
          <div className="space-y-6">
            <AskWorkspace
              availability={qaAvailability}
              suggestions={[
                messages.qa.suggestionSummary,
                messages.qa.suggestionKeyPoints,
                messages.qa.suggestionUseKnowledgeBase
              ]}
              onAsk={(values) =>
                scope === "personal" ? askPersonal.mutateAsync(values) : askTeam.mutateAsync(values)
              }
            />

            {feedback ? (
              <div className={getFeedbackClassName(feedback.tone)}>{feedback.message}</div>
            ) : null}
          </div>

          <div className="space-y-6">
            <Card className="border-border/70 shadow-card">
              <CardHeader>
                <CardTitle>{messages.knowledgeBases.recentConversationsTitle}</CardTitle>
                <CardDescription>{messages.knowledgeBases.recentConversationsDescription}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {recentConversations.length === 0 ? (
                  <div className="rounded-2xl bg-secondary/60 p-4 text-sm text-muted-foreground">
                    {messages.knowledgeBases.recentConversationsEmpty}
                  </div>
                ) : (
                  recentConversations.map((conversation) => (
                    <Link
                      key={conversation.id}
                      href={`/conversations/${conversation.id}`}
                      className="block rounded-2xl border border-border/70 bg-white/80 px-4 py-3 transition-colors hover:bg-accent"
                    >
                      <p className="text-sm font-medium text-foreground">{conversation.title}</p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {messages.common.updatedAt} {formatDate(conversation.updated_at)}
                      </p>
                    </Link>
                  ))
                )}
              </CardContent>
            </Card>

            <Card className="border-border/70 shadow-card">
              <CardHeader>
                <CardTitle>{messages.knowledgeBases.documentsSummaryTitle}</CardTitle>
                <CardDescription>{messages.knowledgeBases.documentsSummaryDescription}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 text-sm text-muted-foreground">
                <div className="rounded-2xl bg-secondary/60 px-4 py-3">
                  {qaAvailability === "empty"
                    ? messages.knowledgeBases.qaEmptyState
                    : qaAvailability === "preparing"
                      ? messages.knowledgeBases.qaPreparingState
                      : qaAvailability === "waiting_review"
                        ? messages.knowledgeBases.qaWaitingReviewState
                        : qaAvailability === "unavailable"
                          ? messages.knowledgeBases.qaUnavailableState
                          : messages.knowledgeBases.qaReadyState}
                </div>
                <Button variant="outline" size="sm" onClick={() => setActiveTab("documents")}>
                  {messages.knowledgeBases.viewAllDocuments}
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
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

          <Card className="border-border/70 shadow-card">
            <CardHeader>
              <CardTitle>{messages.knowledgeBases.documentsTitle}</CardTitle>
              <CardDescription>{messages.knowledgeBases.documentsDescription}</CardDescription>
            </CardHeader>
            <CardContent>
              {documents.length === 0 ? (
                <div className="rounded-2xl bg-secondary/60 p-4 text-sm text-muted-foreground">
                  {messages.knowledgeBases.noDocuments}
                </div>
              ) : (
                <div className="max-h-[520px] space-y-3 overflow-y-auto pr-1">
                  {documents.map((document) => (
                    <DocumentListItem
                      key={document.id}
                      document={document}
                      scope={scope}
                      knowledgeBaseId={knowledgeBaseId}
                      teamId={teamId}
                      isProcessing={processingDocumentIds.includes(document.id)}
                      onProcess={
                        document.processing_status === "failed"
                          ? async () => {
                              await runProcessingPipeline(document);
                            }
                          : null
                      }
                      canDelete={
                        scope === "personal"
                          ? true
                          : Boolean(isTeamAdmin || document.owner_id === currentUser?.id)
                      }
                      deleteDisabledReason={
                        scope === "team" &&
                        !isTeamAdmin &&
                        document.owner_id !== currentUser?.id
                          ? deleteDisabledReason
                          : null
                      }
                      onDelete={() => setPendingDeleteDocument(document)}
                    />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
