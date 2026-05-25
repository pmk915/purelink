"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { useI18n } from "@/hooks/use-i18n";
import type { RetrievalMode } from "@/types";

export function RetrievalDetails({
  retrievalMode,
  usedReranker,
  traceId,
  evidenceCount
}: {
  retrievalMode?: RetrievalMode | string | null;
  usedReranker?: boolean | null;
  traceId?: string | number | null;
  evidenceCount: number;
}) {
  const { messages } = useI18n();
  const [copied, setCopied] = useState(false);

  return (
    <details className="rounded-2xl border border-border/60 bg-secondary/50 px-4 py-3 text-sm text-muted-foreground">
      <summary className="cursor-pointer font-medium text-foreground">
        {messages.qa.retrievalDetails}
      </summary>
      <div className="mt-3 grid gap-2">
        <p>{messages.qa.evidenceCount(evidenceCount)}</p>
        {retrievalMode ? <p>{messages.qa.retrievalMode}: {retrievalMode}</p> : null}
        {typeof usedReranker === "boolean" ? (
          <p>{messages.qa.usedReranker}: {usedReranker ? messages.common.yes : messages.common.no}</p>
        ) : null}
        {traceId ? (
          <div className="flex flex-wrap items-center gap-2">
            <span>Trace ID: {traceId}</span>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-7 rounded-xl px-2 text-xs"
              onClick={async () => {
                await navigator.clipboard?.writeText(String(traceId));
                setCopied(true);
                window.setTimeout(() => setCopied(false), 1200);
              }}
            >
              {copied ? messages.common.copied : messages.common.copy}
            </Button>
          </div>
        ) : null}
        <p>{messages.qa.retrievalDetailsDescription}</p>
      </div>
    </details>
  );
}
