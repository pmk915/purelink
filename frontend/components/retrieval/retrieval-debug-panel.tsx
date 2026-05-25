"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Search } from "lucide-react";
import { useForm } from "react-hook-form";

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
  const form = useForm<RetrievalValues>({
    resolver: zodResolver(retrievalSchema),
    defaultValues: {
      query: "",
      top_k: 8,
      mode: "chunk_only"
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
                await onRetrieve(values);
              } catch (error) {
                console.error("retrieval debug failed", { error });
                form.setError("root", {
                  message: messages.retrievalDebug.failed
                });
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
                  <option value="chunk_only">chunk_only</option>
                  <option value="overview">overview</option>
                  <option value="graph_vector_mix">graph_vector_mix</option>
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

            {form.formState.errors.root?.message ? (
              <div className="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
                {form.formState.errors.root.message}
              </div>
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
          usedReranker={result?.used_reranker}
          traceId={result?.trace_id}
          evidenceCount={result?.results.length ?? 0}
        />
        <EvidencePanel evidences={result?.results ?? []} compact />
      </div>
    </div>
  );
}
