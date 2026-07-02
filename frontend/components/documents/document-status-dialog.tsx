"use client";

import { CheckCircle2, Circle, Copy, LoaderCircle, RotateCcw, TriangleAlert, X } from "lucide-react";
import { useMemo, useState } from "react";

import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { LoadingState } from "@/components/common/loading-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/hooks/use-i18n";
import { cn, formatDate } from "@/lib/utils";
import type { DocumentStatus, DocumentStatusCheck, DocumentStatusCheckState } from "@/types";

type DocumentStatusDialogProps = {
  open: boolean;
  status: DocumentStatus | null | undefined;
  loading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  onRetryProcessing?: () => void;
  retryProcessingLoading?: boolean;
  canRetryProcessing?: boolean;
  onClose: () => void;
};

function badgeVariantForStatus(status: string): "default" | "secondary" | "success" | "warning" | "destructive" | "outline" {
  if (status === "ready" || status === "indexed") {
    return "success";
  }
  if (status === "failed") {
    return "destructive";
  }
  if (status === "warning") {
    return "warning";
  }
  if (status === "missing" || status === "optional") {
    return "outline";
  }
  return "secondary";
}

function iconForStatus(status: DocumentStatusCheckState) {
  if (status === "ready") {
    return <CheckCircle2 className="h-4 w-4 text-emerald-600" />;
  }
  if (status === "failed") {
    return <TriangleAlert className="h-4 w-4 text-rose-600" />;
  }
  if (status === "warning") {
    return <TriangleAlert className="h-4 w-4 text-amber-600" />;
  }
  return <Circle className="h-4 w-4 text-muted-foreground" />;
}

function OverviewTile({
  label,
  value,
  hint
}: {
  label: string;
  value: string | number;
  hint: string;
}) {
  return (
    <div className="rounded-2xl border border-border/70 bg-secondary/40 px-4 py-3">
      <p className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
        {label}
      </p>
      <p className="mt-2 text-lg font-semibold text-foreground">{value}</p>
      <p className="mt-1 truncate text-xs text-muted-foreground">{hint}</p>
    </div>
  );
}

function PipelineCheckRow({
  check,
  statusLabel
}: {
  check: DocumentStatusCheck;
  statusLabel: (status: string) => string;
}) {
  return (
    <div className="flex gap-3 rounded-2xl border border-border/70 bg-white/80 px-4 py-3">
      <div className="mt-0.5 shrink-0">{iconForStatus(check.status)}</div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-medium text-foreground">{check.label}</p>
          <Badge variant={badgeVariantForStatus(check.status)}>
            {statusLabel(check.status)}
          </Badge>
          {typeof check.count === "number" ? (
            <span className="text-xs text-muted-foreground">{check.count}</span>
          ) : null}
        </div>
        <p className="mt-1 break-words text-xs leading-5 text-muted-foreground">
          {check.message}
        </p>
      </div>
    </div>
  );
}

export function DocumentStatusDialog({
  open,
  status,
  loading = false,
  error,
  onRetry,
  onRetryProcessing,
  retryProcessingLoading = false,
  canRetryProcessing = false,
  onClose
}: DocumentStatusDialogProps) {
  const { messages } = useI18n();
  const [copied, setCopied] = useState(false);
  const debugInfo = useMemo(
    () =>
      status
        ? {
            document_id: status.document_id,
            kb_id: status.kb_id,
            filename: status.filename,
            processing_status: status.processing_status,
            rag_ready: status.rag_ready,
            block_count: status.block_count,
            chunk_count: status.chunk_count,
            citation_unit_count: status.citation_unit_count,
            vector_index_status: status.vector_index_status,
            vector_index_count: status.vector_index_count,
            graph_index_status: status.graph_index_status,
            entity_count: status.entity_count,
            relation_count: status.relation_count,
            latest_processing_job_step: status.latest_processing_job_step,
            latest_processing_job_status: status.latest_processing_job_status,
            latest_processing_job_id: status.latest_processing_job_id,
            latest_processing_job_attempt_count: status.latest_processing_job_attempt_count,
            latest_processing_job_max_attempts: status.latest_processing_job_max_attempts,
            latest_processing_job_can_retry: status.latest_processing_job_can_retry,
            latest_processing_job_error_code: status.latest_processing_job_error_code,
            latest_processing_job_error_message: status.latest_processing_job_error_message,
            error_code: status.error_code,
            error_message: status.error_message,
            warnings: status.warnings,
            checks: status.checks
          }
        : null,
    [status]
  );
  const debugJson = debugInfo ? JSON.stringify(debugInfo, null, 2) : "";

  if (!open) {
    return null;
  }

  const copyDebugInfo = async () => {
    if (!debugJson) {
      return;
    }
    await navigator.clipboard.writeText(debugJson);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 px-4 py-6"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="flex max-h-[86vh] w-full max-w-3xl flex-col overflow-hidden rounded-[28px] border border-border/70 bg-white shadow-soft"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="document-status-dialog-title"
      >
        <div className="flex items-start justify-between gap-4 border-b border-border/70 px-6 py-5">
          <div className="min-w-0 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <h2
                id="document-status-dialog-title"
                className="truncate text-lg font-semibold text-foreground"
              >
                {status?.filename ?? messages.documents.statusDialogTitle}
              </h2>
              {status ? (
                <>
                  <Badge variant={badgeVariantForStatus(status.processing_status)}>
                    {messages.documents.statusLabel(status.processing_status)}
                  </Badge>
                  <Badge variant={status.rag_ready ? "success" : "outline"}>
                    {status.rag_ready ? messages.documents.ragReady : messages.documents.notReady}
                  </Badge>
                </>
              ) : null}
            </div>
            <p className="text-sm leading-6 text-muted-foreground">
              {messages.documents.statusDialogDescription}
            </p>
            {status ? (
              <p className="text-xs text-muted-foreground">
                {messages.common.documentId(status.document_id)} · {messages.common.knowledgeBaseId(status.kb_id)}
              </p>
            ) : null}
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label={messages.common.cancel}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          {loading ? (
            <LoadingState message={messages.common.loading} />
          ) : error ? (
            <ErrorState
              title={messages.documents.statusLoadError}
              error={error}
              actionLabel={onRetry ? messages.common.tryAgain : undefined}
              onAction={onRetry}
              requestIdLabel={messages.common.requestId}
            />
          ) : status ? (
            <div className="space-y-6">
              <section className="space-y-3">
                <div>
                  <h3 className="text-sm font-semibold text-foreground">{messages.documents.overview}</h3>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {messages.common.updatedAt} {formatDate(status.updated_at)}
                    {status.last_indexed_at
                      ? ` · ${messages.documents.lastIndexed} ${formatDate(status.last_indexed_at)}`
                      : ""}
                  </p>
                </div>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <OverviewTile
                    label={messages.documents.blocks}
                    value={status.block_count}
                    hint={messages.documents.statusLabel(
                      status.block_count > 0 ? "ready" : "warning"
                    )}
                  />
                  <OverviewTile
                    label={messages.documents.chunks}
                    value={status.chunk_count}
                    hint={messages.documents.statusLabel(
                      status.chunk_count > 0 ? "ready" : "missing"
                    )}
                  />
                  <OverviewTile
                    label={messages.documents.citations}
                    value={status.citation_unit_count}
                    hint={messages.documents.statusLabel(
                      status.citation_unit_count > 0 ? "ready" : "missing"
                    )}
                  />
                  <OverviewTile
                    label={messages.documents.vectorIndex}
                    value={messages.documents.statusLabel(status.vector_index_status)}
                    hint={`${status.vector_index_count} ${messages.documents.chunks}`}
                  />
                </div>
              </section>

              <section className="space-y-3">
                <h3 className="text-sm font-semibold text-foreground">{messages.documents.pipeline}</h3>
                <div className="space-y-2">
                  {status.checks.map((check) => (
                    <PipelineCheckRow
                      key={check.name}
                      check={check}
                      statusLabel={messages.documents.statusLabel}
                    />
                  ))}
                </div>
              </section>

              <section className="space-y-3">
                <h3 className="text-sm font-semibold text-foreground">
                  {messages.documents.warningsAndErrors}
                </h3>
                {status.latest_processing_job_id ? (
                  <div className="rounded-2xl border border-border/70 bg-white/80 px-4 py-3">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-foreground">
                          {messages.processingJobs.latestJob}
                        </p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          #{status.latest_processing_job_id} ·{" "}
                          {status.latest_processing_job_status
                            ? messages.processingJobs.statusLabel(status.latest_processing_job_status)
                            : "-"}{" "}
                          · {messages.processingJobs.currentStep}:{" "}
                          {status.latest_processing_job_step ?? "-"}
                          {status.latest_processing_job_attempt_count
                            ? ` · ${messages.processingJobs.attemptCount(
                                status.latest_processing_job_attempt_count,
                                status.latest_processing_job_max_attempts ??
                                  status.latest_processing_job_attempt_count
                              )}`
                            : ""}
                        </p>
                      </div>
                      {status.latest_processing_job_can_retry && canRetryProcessing ? (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={retryProcessingLoading}
                          onClick={onRetryProcessing}
                        >
                          {retryProcessingLoading ? (
                            <LoaderCircle className="h-4 w-4 animate-spin" />
                          ) : (
                            <RotateCcw className="h-4 w-4" />
                          )}
                          {messages.processingJobs.retry}
                        </Button>
                      ) : null}
                    </div>
                  </div>
                ) : null}
                {status.error_code || status.error_message ? (
                  <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
                    {status.error_code ? (
                      <p>
                        <span className="font-medium">{messages.documents.errorCode}: </span>
                        {status.error_code}
                      </p>
                    ) : null}
                    {status.error_message ? (
                      <p className="mt-1 break-words">
                        <span className="font-medium">{messages.documents.errorMessage}: </span>
                        {status.error_message}
                      </p>
                    ) : null}
                    {status.latest_processing_job_step ? (
                      <p className="mt-1">
                        <span className="font-medium">{messages.documents.latestStep}: </span>
                        {status.latest_processing_job_step}
                      </p>
                    ) : null}
                  </div>
                ) : status.warnings.length > 0 ? (
                  <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                    <ul className="space-y-1">
                      {status.warnings.map((warning) => (
                        <li key={warning} className="break-words">
                          {warning}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <div className="rounded-2xl bg-secondary/60 px-4 py-3 text-sm text-muted-foreground">
                    {messages.documents.noWarnings}
                  </div>
                )}

                {!status.rag_ready ? (
                  <div className="rounded-2xl border border-border/70 bg-white/80 px-4 py-3">
                    <p className="text-sm font-medium text-foreground">
                      {messages.documents.possibleReasons}
                    </p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {status.checks
                        .filter((check) => ["missing", "failed", "warning"].includes(check.status))
                        .map((check) => (
                          <Badge key={check.name} variant={badgeVariantForStatus(check.status)}>
                            {check.label}
                          </Badge>
                        ))}
                    </div>
                  </div>
                ) : null}
              </section>

              <section className="space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-sm font-semibold text-foreground">{messages.documents.debugInfo}</h3>
                  <Button variant="outline" size="sm" onClick={copyDebugInfo}>
                    <Copy className="h-4 w-4" />
                    {messages.documents.copyDebugInfo}
                  </Button>
                </div>
                <pre className="max-h-48 overflow-auto rounded-2xl border border-border/70 bg-slate-950 px-4 py-3 text-xs leading-5 text-slate-100">
                  {debugJson}
                </pre>
              </section>
            </div>
          ) : (
            <EmptyState
              title={messages.documents.diagnosticsMissing}
              message={messages.documents.statusDialogDescription}
            />
          )}
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-border/70 px-6 py-4">
          <p
            className={cn(
              "text-xs text-muted-foreground transition-opacity",
              copied ? "opacity-100" : "opacity-0"
            )}
          >
            {messages.documents.copiedDebugInfo}
          </p>
          <div className="flex items-center gap-3">
            <Button variant="ghost" onClick={onClose}>
              {messages.common.cancel}
            </Button>
            <Button variant="outline" onClick={copyDebugInfo} disabled={!debugJson}>
              <Copy className="h-4 w-4" />
              {messages.documents.copyDebugInfo}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
