"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { MessageSquarePlus, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { ErrorState } from "@/components/common/error-state";
import { EvidencePanel } from "@/components/qa/evidence-panel";
import { RetrievalDetails } from "@/components/qa/retrieval-details";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/hooks/use-i18n";
import { askSchema, type AskValues } from "@/schemas/qa";
import type { AskResponse } from "@/types";

export type QaAvailability =
  | "ready"
  | "empty"
  | "waiting_review"
  | "preparing"
  | "unavailable";

export function AskWorkspace({
  availability,
  onAsk,
  suggestions = []
}: {
  availability: QaAvailability;
  onAsk: (values: AskValues) => Promise<AskResponse>;
  suggestions?: string[];
}) {
  const router = useRouter();
  const { messages } = useI18n();
  const [latestAnswer, setLatestAnswer] = useState<AskResponse | null>(null);
  const [askError, setAskError] = useState<unknown>(null);

  const askForm = useForm<AskValues>({
    resolver: zodResolver(askSchema),
    defaultValues: {
      question: "",
      top_k: 5,
      conversation_id: null,
      mode: "auto"
    }
  });

  const canAsk = availability === "ready";
  const availabilityMessage = {
    ready: null,
    empty: messages.qa.noQueryableDocuments,
    waiting_review: messages.qa.documentsWaitingReview,
    preparing: messages.qa.documentsPreparing,
    unavailable: messages.qa.noAvailableDocuments
  }[availability];

  return (
    <Card className="border-border/70 shadow-card">
      <CardHeader className="space-y-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-primary/10 text-primary">
            <Sparkles className="h-5 w-5" />
          </div>
          <div className="space-y-1">
            <CardTitle>{messages.qa.askTitle}</CardTitle>
            <CardDescription>{messages.qa.askDescription}</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        {availabilityMessage ? (
          <div className="rounded-2xl bg-secondary/70 px-4 py-3 text-sm text-muted-foreground">
            {availabilityMessage}
          </div>
        ) : null}

        <form
          className="space-y-4"
          onSubmit={askForm.handleSubmit(async (values) => {
            if (!canAsk) {
              return;
            }

            try {
              setAskError(null);
              const result = await onAsk(values);
              setLatestAnswer(result);
              askForm.reset({
                question: "",
                top_k: values.top_k,
                conversation_id: result.conversation_id,
                mode: "auto"
              });
            } catch (error) {
              console.error("ask failed", { error });
              setAskError(error);
            }
          })}
        >
          <div className="space-y-2">
            <Label htmlFor="ask-question">{messages.qa.askQuestion}</Label>
            <Textarea
              id="ask-question"
              rows={5}
              disabled={!canAsk}
              placeholder={messages.qa.askPlaceholder}
              {...askForm.register("question")}
            />
            <p className="text-xs text-rose-600">{askForm.formState.errors.question?.message}</p>
          </div>

          {suggestions.length > 0 ? (
            <div className="space-y-3">
              <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
                {messages.qa.suggestedQuestions}
              </p>
              <div className="flex flex-wrap gap-2">
                {suggestions.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    className="rounded-full border border-border bg-background px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                    onClick={() => askForm.setValue("question", suggestion, { shouldValidate: true })}
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {askError ? (
            <ErrorState
              title={messages.qa.askFailed}
              error={askError}
              requestIdLabel={messages.common.requestId}
            />
          ) : null}

          <Button disabled={!canAsk || askForm.formState.isSubmitting}>
            {askForm.formState.isSubmitting ? (
              <MessageSquarePlus className="h-4 w-4 animate-pulse" />
            ) : (
              <Sparkles className="h-4 w-4" />
            )}
            {askForm.formState.isSubmitting ? messages.qa.asking : messages.qa.askSubmit}
          </Button>
        </form>

        {latestAnswer ? (
          <div className="space-y-4 border-t border-border/60 pt-5">
            <div className="rounded-2xl bg-secondary/60 px-4 py-3">
              <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
                {messages.qa.answerTitle}
              </p>
              <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-foreground">
                {latestAnswer.answer}
              </p>
            </div>
            <RetrievalDetails
              retrievalMode={latestAnswer.retrieval_mode}
              requestedMode={latestAnswer.requested_mode}
              selectedMode={latestAnswer.selected_mode}
              routerReason={latestAnswer.router_reason}
              usedReranker={latestAnswer.used_reranker}
              traceId={latestAnswer.trace_id}
              evidenceCount={latestAnswer.citations.length}
            />
            <EvidencePanel evidences={latestAnswer.citations} compact />
            <Button
              type="button"
              variant="outline"
              className="rounded-xl"
              onClick={() => router.push(`/conversations/${latestAnswer.conversation_id}`)}
            >
              {messages.qa.openConversation(latestAnswer.conversation_id)}
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
