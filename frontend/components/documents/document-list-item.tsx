"use client";

import Link from "next/link";
import { FileText, Info, LoaderCircle, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { useI18n } from "@/hooks/use-i18n";
import { cn, formatBytes, formatDate } from "@/lib/utils";
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

function buildPreviewHref(
  scope: KnowledgeBaseScope,
  knowledgeBaseId: number,
  documentId: number,
  teamId?: number
) {
  if (scope === "team" && teamId) {
    return `/teams/${teamId}/knowledge-bases/${knowledgeBaseId}/documents/${documentId}/preview`;
  }

  return `/knowledge-bases/${knowledgeBaseId}/documents/${documentId}/preview`;
}

export function DocumentListItem({
  document,
  scope,
  knowledgeBaseId,
  teamId,
  onProcess,
  isProcessing,
  onDelete,
  onViewStatus,
  canDelete = false,
  deleteDisabledReason
}: {
  document: Document;
  scope: KnowledgeBaseScope;
  knowledgeBaseId: number;
  teamId?: number;
  onProcess?: (() => Promise<void> | void) | null;
  isProcessing?: boolean;
  onDelete?: (() => void) | null;
  onViewStatus?: (() => void) | null;
  canDelete?: boolean;
  deleteDisabledReason?: string | null;
}) {
  const { messages } = useI18n();
  const isSupported = supportsDocumentPreparation(document.original_filename);
  const failureHint =
    document.latest_processing_job_error_code &&
    document.latest_processing_job_error_code in messages.documents.failureHints
      ? messages.documents.failureHints[
          document.latest_processing_job_error_code as keyof typeof messages.documents.failureHints
        ]
      : messages.documents.statusFailedHint;
  const hasActiveProcessingJob =
    (document.latest_processing_job_status === "queued" ||
      document.latest_processing_job_status === "processing" ||
      document.latest_processing_job_status === "retrying") &&
    document.latest_processing_job_type === "document_process";
  const hasActiveJob =
    document.latest_processing_job_status === "queued" ||
    document.latest_processing_job_status === "processing" ||
    document.latest_processing_job_status === "retrying";

  const status = (() => {
    if (isProcessing || hasActiveProcessingJob) {
      return {
        label: messages.documents.statusProcessing,
        description: messages.documents.statusProcessingHint,
        variant: "secondary" as const
      };
    }

    if (document.review_status === "pending_review") {
      return {
        label: messages.documents.statusPendingReview,
        description: messages.documents.statusPendingReviewHint,
        variant: "secondary" as const
      };
    }

    if (document.review_status === "rejected") {
      return {
        label: messages.documents.statusRejected,
        description: messages.documents.statusRejectedHint,
        variant: "destructive" as const
      };
    }

    if (!isSupported) {
      return {
        label: messages.documents.statusUnsupported,
        description: messages.documents.statusUnsupportedHint,
        variant: "outline" as const
      };
    }

    if (
      document.processing_status === "ready" ||
      document.processing_status === "indexed"
    ) {
      return {
        label: messages.documents.statusAvailable,
        description: messages.documents.statusAvailableHint,
        variant: "default" as const
      };
    }

    if (document.processing_status === "processing" || document.processing_status === "parsed") {
      return {
        label: messages.documents.statusProcessing,
        description: messages.documents.statusProcessingHint,
        variant: "secondary" as const
      };
    }

    if (document.processing_status === "failed") {
      return {
        label: messages.documents.statusFailed,
        description: failureHint,
        variant: "destructive" as const
      };
    }

    return {
      label: messages.documents.statusUploaded,
      description: messages.documents.statusUploadedHint,
      variant: "outline" as const
    };
  })();

  const canRetry =
    Boolean(onProcess) &&
    isSupported &&
    document.review_status !== "pending_review" &&
    document.review_status !== "rejected" &&
    !hasActiveJob &&
    document.processing_status === "failed";

  return (
    <div className="rounded-2xl border border-border/70 bg-white/80 px-4 py-3 shadow-soft">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="min-w-0 space-y-1.5">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-secondary text-muted-foreground">
              <FileText className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-foreground">
                {document.original_filename}
              </p>
              <p className="truncate text-xs text-muted-foreground">
                {document.file_type} · {formatBytes(document.file_size)} ·{" "}
                {messages.documents.uploadedAt} {formatDate(document.created_at)}
              </p>
            </div>
          </div>
          {(document.review_comment || status.description) ? (
            <p className="truncate pl-12 text-xs text-muted-foreground">
              {document.review_comment
                ? `${messages.documents.reviewComment}: ${document.review_comment}`
                : status.description}
            </p>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-2 pl-12 md:pl-0">
          <Badge variant={status.variant}>{status.label}</Badge>
          <Link
            href={buildPreviewHref(scope, knowledgeBaseId, document.id, teamId)}
            className={cn(
              buttonVariants({
                variant: "outline",
                size: "sm"
              })
            )}
          >
            {messages.common.open}
          </Link>
          {onViewStatus ? (
            <Button size="sm" variant="outline" onClick={onViewStatus}>
              <Info className="h-4 w-4" />
              {messages.documents.viewStatus}
            </Button>
          ) : null}
          {canRetry ? (
            <Button
              size="sm"
              variant="outline"
              disabled={isProcessing || hasActiveProcessingJob}
              onClick={onProcess ?? undefined}
            >
              {isProcessing || hasActiveProcessingJob ? (
                <LoaderCircle className="h-4 w-4 animate-spin" />
              ) : null}
              {messages.documents.processRetry}
            </Button>
          ) : null}
          {onDelete || deleteDisabledReason ? (
            <Button
              size="sm"
              variant="ghost"
              className="text-rose-600 hover:bg-rose-50 hover:text-rose-700"
              disabled={!canDelete}
              title={!canDelete ? deleteDisabledReason ?? undefined : undefined}
              onClick={canDelete ? onDelete ?? undefined : undefined}
            >
              <Trash2 className="h-4 w-4" />
              {messages.common.delete}
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
