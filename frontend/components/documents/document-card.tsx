"use client";

import { LoaderCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useI18n } from "@/hooks/use-i18n";
import type { Document } from "@/types";
import { formatBytes, formatDate } from "@/lib/utils";

function supportsDocumentPreparation(filename: string) {
  const normalized = filename.toLowerCase();
  return (
    normalized.endsWith(".txt") ||
    normalized.endsWith(".md") ||
    normalized.endsWith(".pdf") ||
    normalized.endsWith(".docx") ||
    normalized.endsWith(".mp3") ||
    normalized.endsWith(".wav") ||
    normalized.endsWith(".m4a") ||
    normalized.endsWith(".mp4") ||
    normalized.endsWith(".mov") ||
    normalized.endsWith(".m4v") ||
    normalized.endsWith(".png") ||
    normalized.endsWith(".jpg") ||
    normalized.endsWith(".jpeg")
  );
}

export function DocumentCard({
  document,
  onProcess,
  isProcessing
}: {
  document: Document;
  onProcess?: (() => Promise<void> | void) | null;
  isProcessing?: boolean;
}) {
  const { messages } = useI18n();
  const isSupported = supportsDocumentPreparation(document.original_filename);
  const hasActiveProcessingJob =
    (document.latest_processing_job_status === "queued" ||
      document.latest_processing_job_status === "running") &&
    document.latest_processing_job_type === "document_process";
  const hasActiveJob =
    document.latest_processing_job_status === "queued" ||
    document.latest_processing_job_status === "running";

  const status = (() => {
    if (isProcessing || hasActiveProcessingJob) {
      return {
        label: messages.documents.statusProcessing,
        description: messages.documents.statusProcessingHint,
        variant: "warning" as const
      };
    }

    if (document.review_status === "pending_review") {
      return {
        label: messages.documents.statusPendingReview,
        description: messages.documents.statusPendingReviewHint,
        variant: "warning" as const
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
        variant: "success" as const
      };
    }

    if (document.processing_status === "processing") {
      return {
        label: messages.documents.statusProcessing,
        description: messages.documents.statusProcessingHint,
        variant: "warning" as const
      };
    }

    if (document.processing_status === "failed") {
      return {
        label: messages.documents.statusFailed,
        description: messages.documents.statusFailedHint,
        variant: "destructive" as const
      };
    }

    if (document.processing_status === "parsed") {
      return {
        label: messages.documents.statusProcessing,
        description: messages.documents.statusProcessingHint,
        variant: "warning" as const
      };
    }

    return {
      label: messages.documents.statusUploaded,
      description: messages.documents.statusUploadedHint,
      variant: "secondary" as const
    };
  })();

  const processButtonLabel = messages.documents.processRetry;

  const canProcess =
    Boolean(onProcess) &&
    isSupported &&
    document.review_status !== "pending_review" &&
    document.review_status !== "rejected" &&
    !hasActiveJob &&
    document.processing_status !== "processing" &&
    document.processing_status !== "ready" &&
    document.processing_status !== "indexed";

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <CardTitle>{document.original_filename}</CardTitle>
            <CardDescription className="mt-2">
              {document.file_type} · {formatBytes(document.file_size)} · {messages.documents.uploadedAt}{" "}
              {formatDate(document.created_at)}
            </CardDescription>
          </div>
          <Badge variant={status.variant}>{status.label}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="rounded-2xl bg-secondary/60 px-4 py-3 text-sm text-muted-foreground">
          {status.description}
        </div>

        {document.review_comment ? (
          <div className="rounded-2xl bg-amber-50 px-4 py-3 text-sm text-amber-800">
            {messages.documents.reviewComment}: {document.review_comment}
          </div>
        ) : null}

        {canProcess ? (
          <Button disabled={isProcessing || hasActiveProcessingJob} onClick={onProcess ?? undefined}>
            {isProcessing || hasActiveProcessingJob ? (
              <LoaderCircle className="h-4 w-4 animate-spin" />
            ) : null}
            {isProcessing || hasActiveProcessingJob
              ? messages.documents.processingNow
              : processButtonLabel}
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}
