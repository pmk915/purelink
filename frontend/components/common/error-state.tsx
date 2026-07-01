import { AlertCircle } from "lucide-react";

import { ApiError } from "@/api/errors";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function ErrorState({
  title,
  message,
  code,
  requestId,
  error,
  requestIdLabel = "Request ID",
  actionLabel,
  onAction,
  variant = "inline",
  className
}: {
  title: string;
  message?: string;
  code?: string | null;
  requestId?: string | null;
  error?: unknown;
  requestIdLabel?: string;
  actionLabel?: string;
  onAction?: () => void;
  variant?: "inline" | "card";
  className?: string;
}) {
  const apiError = error instanceof ApiError ? error : null;
  const displayMessage =
    message ?? (error instanceof Error ? error.message : null) ?? title;
  const displayCode = code ?? apiError?.code ?? null;
  const displayRequestId = requestId ?? apiError?.requestId ?? null;

  return (
    <div
      className={cn(
        "rounded-2xl border border-rose-200 bg-rose-50/80 px-4 py-3 text-sm text-rose-800",
        variant === "card" && "p-5",
        className
      )}
      role="alert"
    >
      <div className="flex gap-3">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-rose-600" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-medium text-rose-900">{title}</p>
            {displayCode ? <Badge variant="destructive">{displayCode}</Badge> : null}
          </div>
          <p className="mt-1 break-words leading-6">{displayMessage}</p>
          {displayRequestId ? (
            <p className="mt-2 break-all text-xs text-rose-700/80">
              {requestIdLabel}: {displayRequestId}
            </p>
          ) : null}
          {actionLabel && onAction ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="mt-3 border-rose-200 bg-white/70 text-rose-900 hover:bg-rose-100"
              onClick={onAction}
            >
              {actionLabel}
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
