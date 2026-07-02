"use client";

import { LoaderCircle, RefreshCw, RotateCcw, Search } from "lucide-react";
import { useState } from "react";

import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { LoadingState } from "@/components/common/loading-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useI18n } from "@/hooks/use-i18n";
import { cn, formatDate } from "@/lib/utils";
import type { ProcessingJobList, ProcessingJobStatus, ProcessingJobSummary } from "@/types";

type ProcessingJobFilter = "all" | ProcessingJobStatus;

const FILTERS: ProcessingJobFilter[] = [
  "all",
  "queued",
  "processing",
  "failed",
  "succeeded",
  "cancelled"
];

function badgeVariantForJobStatus(
  status: ProcessingJobStatus
): "default" | "secondary" | "success" | "warning" | "destructive" | "outline" {
  if (status === "succeeded") {
    return "success";
  }
  if (status === "failed" || status === "cancelled") {
    return "destructive";
  }
  if (status === "queued" || status === "processing" || status === "retrying") {
    return "secondary";
  }
  return "outline";
}

function SummaryTile({
  label,
  value,
  hint
}: {
  label: string;
  value: number;
  hint: string;
}) {
  return (
    <div className="rounded-2xl border border-border/70 bg-secondary/50 px-4 py-3">
      <p className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
        {label}
      </p>
      <p className="mt-2 text-lg font-semibold text-foreground">{value}</p>
      <p className="mt-1 truncate text-xs text-muted-foreground">{hint}</p>
    </div>
  );
}

function JobRow({
  job,
  canRetry,
  retrying,
  onRetry
}: {
  job: ProcessingJobSummary;
  canRetry: boolean;
  retrying: boolean;
  onRetry?: (job: ProcessingJobSummary) => void;
}) {
  const { messages } = useI18n();
  const showRetry = job.can_retry && canRetry;

  return (
    <div className="rounded-2xl border border-border/70 bg-white/80 px-4 py-3">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-medium text-foreground">{job.filename}</p>
            <Badge variant={badgeVariantForJobStatus(job.status)}>
              {messages.processingJobs.statusLabel(job.status)}
            </Badge>
            <Badge variant="outline">
              {messages.processingJobs.jobTypeLabel(job.job_type)}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground">
            {messages.common.documentId(job.document_id)} ·{" "}
            {messages.processingJobs.currentStep}: {job.current_step ?? "-"} ·{" "}
            {messages.processingJobs.attemptCount(job.attempt_count, job.max_attempts)}
          </p>
          {job.error_code || job.error_message ? (
            <div className="rounded-xl border border-rose-200 bg-rose-50/80 px-3 py-2 text-xs leading-5 text-rose-800">
              {job.error_code ? (
                <p>
                  <span className="font-medium">{messages.common.errorCode}: </span>
                  {job.error_code}
                </p>
              ) : null}
              {job.error_message ? <p className="break-words">{job.error_message}</p> : null}
            </div>
          ) : null}
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span>{messages.common.updatedAt} {formatDate(job.updated_at)}</span>
          {showRetry ? (
            <Button
              size="sm"
              variant="outline"
              disabled={retrying}
              onClick={() => onRetry?.(job)}
            >
              {retrying ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
              {messages.processingJobs.retry}
            </Button>
          ) : job.can_retry ? (
            <span className="rounded-full border border-border/70 px-3 py-1">
              {messages.processingJobs.adminOnly}
            </span>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function ProcessingJobDashboard({
  data,
  loading,
  error,
  refreshing,
  retryingDocumentId,
  canRetry,
  onRefresh,
  onRetry,
  onFilterChange
}: {
  data: ProcessingJobList | undefined;
  loading: boolean;
  error: unknown;
  refreshing: boolean;
  retryingDocumentId: number | null;
  canRetry: boolean;
  onRefresh: () => void;
  onRetry: (job: ProcessingJobSummary) => void;
  onFilterChange: (values: { status: ProcessingJobFilter; search: string }) => void;
}) {
  const { messages } = useI18n();
  const [status, setStatus] = useState<ProcessingJobFilter>("all");
  const [search, setSearch] = useState("");

  const updateFilter = (nextStatus: ProcessingJobFilter, nextSearch: string) => {
    setStatus(nextStatus);
    setSearch(nextSearch);
    onFilterChange({ status: nextStatus, search: nextSearch });
  };

  return (
    <Card className="border-border/70 shadow-card">
      <CardHeader className="space-y-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <CardTitle>{messages.processingJobs.title}</CardTitle>
            <CardDescription>{messages.processingJobs.description}</CardDescription>
          </div>
          <Button size="sm" variant="outline" onClick={onRefresh} disabled={refreshing}>
            <RefreshCw className={cn("h-4 w-4", refreshing && "animate-spin")} />
            {messages.processingJobs.refresh}
          </Button>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <SummaryTile
            label={messages.processingJobs.running}
            value={data?.running_count ?? 0}
            hint={messages.processingJobs.runningHint}
          />
          <SummaryTile
            label={messages.processingJobs.failed}
            value={data?.failed_count ?? 0}
            hint={messages.processingJobs.failedHint}
          />
          <SummaryTile
            label={messages.processingJobs.completed}
            value={data?.completed_count ?? 0}
            hint={messages.processingJobs.completedHint}
          />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap gap-2">
            {FILTERS.map((filter) => (
              <Button
                key={filter}
                size="sm"
                variant={status === filter ? "default" : "outline"}
                onClick={() => updateFilter(filter, search)}
              >
                {filter === "all"
                  ? messages.processingJobs.all
                  : messages.processingJobs.statusLabel(filter)}
              </Button>
            ))}
          </div>
          <label className="flex min-w-0 items-center gap-2 rounded-2xl border border-border/70 bg-white px-3 py-2 text-sm text-muted-foreground lg:w-72">
            <Search className="h-4 w-4 shrink-0" />
            <input
              value={search}
              onChange={(event) => updateFilter(status, event.target.value)}
              placeholder={messages.processingJobs.searchPlaceholder}
              className="min-w-0 flex-1 bg-transparent text-foreground outline-none placeholder:text-muted-foreground"
            />
          </label>
        </div>

        {loading ? (
          <LoadingState message={messages.processingJobs.loading} />
        ) : error ? (
          <ErrorState
            title={messages.processingJobs.loadError}
            error={error}
            actionLabel={messages.common.tryAgain}
            onAction={onRefresh}
            requestIdLabel={messages.common.requestId}
          />
        ) : !data || data.items.length === 0 ? (
          <EmptyState
            title={messages.processingJobs.emptyTitle}
            message={messages.processingJobs.emptyDescription}
          />
        ) : (
          <div className="max-h-[420px] space-y-3 overflow-y-auto pr-1">
            {data.items.map((job) => (
              <JobRow
                key={job.id}
                job={job}
                canRetry={canRetry}
                retrying={retryingDocumentId === job.document_id}
                onRetry={onRetry}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
