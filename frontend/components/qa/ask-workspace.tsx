"use client";

import Link from "next/link";
import { zodResolver } from "@hookform/resolvers/zod";
import { Sparkles } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";

import { CitationCard } from "@/components/qa/citation-card";
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
  onAsk
}: {
  availability: QaAvailability;
  onAsk: (values: AskValues) => Promise<AskResponse>;
}) {
  const { messages } = useI18n();
  const [answerResult, setAnswerResult] = useState<AskResponse | null>(null);
  const [activeConversationId, setActiveConversationId] = useState<number | null>(null);

  const askForm = useForm<AskValues>({
    resolver: zodResolver(askSchema),
    defaultValues: {
      question: "",
      top_k: 5,
      conversation_id: null
    }
  });

  const citations = useMemo(
    () => answerResult?.citations ?? [],
    [answerResult]
  );
  const canAsk = availability === "ready";
  const availabilityMessage = {
    ready: null,
    empty: messages.qa.noQueryableDocuments,
    waiting_review: messages.qa.documentsWaitingReview,
    preparing: messages.qa.documentsPreparing,
    unavailable: messages.qa.noAvailableDocuments
  }[availability];

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1.5fr)_380px]">
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>{messages.qa.askTitle}</CardTitle>
            <CardDescription>{messages.qa.askDescription}</CardDescription>
          </CardHeader>
          <CardContent>
            <form
              className="space-y-4"
              onSubmit={askForm.handleSubmit(async (values) => {
                if (!canAsk) {
                  return;
                }

                try {
                  const result = await onAsk({
                    ...values,
                    conversation_id: activeConversationId
                  });
                  setAnswerResult(result);
                  setActiveConversationId(result.conversation_id);
                } catch (error) {
                  console.error("ask failed", { error });
                  askForm.setError("root", {
                    message: messages.qa.askFailed
                  });
                }
              })}
            >
              {availabilityMessage ? (
                <div className="rounded-2xl bg-secondary/70 px-4 py-3 text-sm text-muted-foreground">
                  {availabilityMessage}
                </div>
              ) : null}
              <div className="space-y-2">
                <Label htmlFor="ask-question">{messages.qa.askQuestion}</Label>
                <Textarea
                  id="ask-question"
                  rows={5}
                  disabled={!canAsk}
                  {...askForm.register("question")}
                />
                <p className="text-xs text-rose-600">{askForm.formState.errors.question?.message}</p>
              </div>
              {askForm.formState.errors.root?.message ? (
                <div className="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
                  {askForm.formState.errors.root.message}
                </div>
              ) : null}
              <div className="flex flex-wrap items-center gap-3">
                <Button disabled={!canAsk || askForm.formState.isSubmitting}>
                  <Sparkles className="h-4 w-4" />
                  {askForm.formState.isSubmitting ? messages.qa.asking : messages.qa.askSubmit}
                </Button>
                {activeConversationId ? (
                  <Link
                    href={`/conversations/${activeConversationId}`}
                    className="text-sm font-medium text-primary"
                  >
                    {messages.qa.openConversation(activeConversationId)}
                  </Link>
                ) : null}
              </div>
            </form>

            {answerResult ? (
              <div className="mt-6 rounded-3xl bg-secondary/60 p-5">
                <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
                  {messages.qa.answerTitle}
                </p>
                <p className="mt-3 whitespace-pre-wrap leading-7 text-foreground">
                  {answerResult.answer}
                </p>
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>

      <Card className="h-fit xl:sticky xl:top-28">
        <CardHeader>
          <CardTitle>{messages.qa.citationsTitle}</CardTitle>
          <CardDescription>{messages.qa.citationsDescription}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {citations.length === 0 ? (
            <div className="rounded-2xl bg-secondary/60 p-4 text-sm text-muted-foreground">
              {answerResult ? messages.qa.noReliableSources : messages.qa.citationsEmpty}
            </div>
          ) : null}
          {citations.map((citation) => (
            <CitationCard
              key={`${citation.document_id}-${citation.chunk_id}-${citation.citation_unit_id ?? "chunk"}`}
              citation={citation}
            />
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
