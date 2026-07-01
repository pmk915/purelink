"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Search } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { ErrorState } from "@/components/common/error-state";
import { EvidencePanel } from "@/components/qa/evidence-panel";
import { RetrievalDetails } from "@/components/qa/retrieval-details";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useI18n } from "@/hooks/use-i18n";
import { retrievalSchema, type RetrievalValues } from "@/schemas/qa";
import type { RetrievalResponse } from "@/types";

export function RetrievalDebugPanel({
  onRetrieve,
  isRunning,
  result
}: {
  onRetrieve: (values: RetrievalValues) => Promise<RetrievalResponse>;
  isRunning: boolean;
  result: RetrievalResponse | null;
}) {
  const { messages } = useI18n();
  const [runError, setRunError] = useState<unknown>(null);
  const form = useForm<RetrievalValues>({
    resolver: zodResolver(retrievalSchema),
    defaultValues: {
      query: "",
      top_k: 8,
      mode: "auto"
    }
  });

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
      <Card className="border-border/70 shadow-card">
        <CardHeader>
          <CardTitle>{messages.retrievalDebug.title}</CardTitle>
          <CardDescription>{messages.retrievalDebug.description}</CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="grid gap-4"
            onSubmit={form.handleSubmit(async (values) => {
              try {
                setRunError(null);
                await onRetrieve(values);
              } catch (error) {
                console.error("retrieval debug failed", { error });
                setRunError(error);
              }
            })}
          >
            <div className="space-y-2">
              <Label htmlFor="retrieval-debug-query">{messages.retrievalDebug.query}</Label>
              <Input
                id="retrieval-debug-query"
                placeholder={messages.retrievalDebug.queryPlaceholder}
                {...form.register("query")}
              />
              <p className="text-xs text-rose-600">{form.formState.errors.query?.message}</p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="retrieval-debug-mode">{messages.retrievalDebug.mode}</Label>
                <select
                  id="retrieval-debug-mode"
                  className="flex h-10 w-full rounded-xl border border-input bg-background px-3 py-2 text-sm"
                  {...form.register("mode")}
                >
                  <option value="auto">{messages.qa.retrievalModeLabel("auto")}</option>
                  <option value="chunk_only">{messages.qa.retrievalModeLabel("chunk_only")}</option>
                  <option value="overview">{messages.qa.retrievalModeLabel("overview")}</option>
                  <option value="graph_vector_mix">{messages.qa.retrievalModeLabel("graph_vector_mix")}</option>
                  <option value="hybrid_text">{messages.retrievalDebug.hybridTextMode}</option>
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="retrieval-debug-top-k">top_k</Label>
                <Input
                  id="retrieval-debug-top-k"
                  type="number"
                  min={1}
                  max={20}
                  {...form.register("top_k", { valueAsNumber: true })}
                />
              </div>
            </div>

            {runError ? (
              <ErrorState
                title={messages.retrievalDebug.failed}
                error={runError}
                requestIdLabel={messages.common.requestId}
              />
            ) : null}

            <Button disabled={isRunning}>
              <Search className="h-4 w-4" />
              {isRunning ? messages.retrievalDebug.running : messages.retrievalDebug.run}
            </Button>
          </form>
        </CardContent>
      </Card>

      <div className="space-y-4">
        <RetrievalDetails
          retrievalMode={result?.mode}
          requestedMode={result?.requested_mode}
          selectedMode={result?.selected_mode}
          routerReason={result?.router_reason}
          usedReranker={result?.used_reranker}
          traceId={result?.trace_id}
          evidenceCount={result?.results.length ?? 0}
        />
        <EvidencePanel evidences={result?.results ?? []} compact />
      </div>
    </div>
  );
}
