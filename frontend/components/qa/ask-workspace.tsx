"use client";

import Link from "next/link";
import { zodResolver } from "@hookform/resolvers/zod";
import { Search, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/hooks/use-i18n";
import { askSchema, retrievalSchema, type AskValues, type RetrievalValues } from "@/schemas/qa";
import type { AskResponse, RetrievalResponse } from "@/types";

export function AskWorkspace({
  scopeLabel,
  onRetrieve,
  onAsk
}: {
  scopeLabel: string;
  onRetrieve: (values: RetrievalValues) => Promise<RetrievalResponse>;
  onAsk: (values: AskValues) => Promise<AskResponse>;
}) {
  const { messages } = useI18n();
  const [retrievalResult, setRetrievalResult] = useState<RetrievalResponse | null>(null);
  const [answerResult, setAnswerResult] = useState<AskResponse | null>(null);
  const [activeConversationId, setActiveConversationId] = useState<number | null>(null);

  const retrieveForm = useForm<RetrievalValues>({
    resolver: zodResolver(retrievalSchema),
    defaultValues: {
      query: "",
      top_k: 5
    }
  });

  const askForm = useForm<AskValues>({
    resolver: zodResolver(askSchema),
    defaultValues: {
      question: "",
      top_k: 5,
      conversation_id: null
    }
  });

  const citations = useMemo(
    () => answerResult?.citations ?? retrievalResult?.results ?? [],
    [answerResult, retrievalResult]
  );

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1.5fr)_380px]">
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>{messages.qa.retrieveTitle}</CardTitle>
            <CardDescription>{messages.qa.retrieveDescription(scopeLabel)}</CardDescription>
          </CardHeader>
          <CardContent>
            <form
              className="space-y-4"
              onSubmit={retrieveForm.handleSubmit(async (values) => {
                try {
                  const result = await onRetrieve(values);
                  setRetrievalResult(result);
                  setAnswerResult(null);
                } catch (error) {
                  retrieveForm.setError("root", {
                    message:
                      error instanceof Error ? error.message : messages.qa.retrieveFailed
                  });
                }
              })}
            >
              <div className="space-y-2">
                <Label htmlFor="retrieve-query">{messages.qa.retrieveQuery}</Label>
                <Input id="retrieve-query" {...retrieveForm.register("query")} />
                <p className="text-xs text-rose-600">{retrieveForm.formState.errors.query?.message}</p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="retrieve-top-k">{messages.qa.retrieveTopK}</Label>
                <Input
                  id="retrieve-top-k"
                  type="number"
                  min={1}
                  max={20}
                  {...retrieveForm.register("top_k", { valueAsNumber: true })}
                />
              </div>
              {retrieveForm.formState.errors.root?.message ? (
                <div className="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
                  {retrieveForm.formState.errors.root.message}
                </div>
              ) : null}
              <Button disabled={retrieveForm.formState.isSubmitting}>
                <Search className="h-4 w-4" />
                {retrieveForm.formState.isSubmitting
                  ? messages.qa.retrieving
                  : messages.qa.retrieveSubmit}
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{messages.qa.askTitle}</CardTitle>
            <CardDescription>{messages.qa.askDescription}</CardDescription>
          </CardHeader>
          <CardContent>
            <form
              className="space-y-4"
              onSubmit={askForm.handleSubmit(async (values) => {
                try {
                  const result = await onAsk({
                    ...values,
                    conversation_id: activeConversationId
                  });
                  setAnswerResult(result);
                  setActiveConversationId(result.conversation_id);
                } catch (error) {
                  askForm.setError("root", {
                    message: error instanceof Error ? error.message : messages.qa.askFailed
                  });
                }
              })}
            >
              <div className="space-y-2">
                <Label htmlFor="ask-question">{messages.qa.askQuestion}</Label>
                <Textarea id="ask-question" rows={5} {...askForm.register("question")} />
                <p className="text-xs text-rose-600">{askForm.formState.errors.question?.message}</p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="ask-top-k">{messages.qa.askTopK}</Label>
                <Input
                  id="ask-top-k"
                  type="number"
                  min={1}
                  max={20}
                  {...askForm.register("top_k", { valueAsNumber: true })}
                />
              </div>
              {askForm.formState.errors.root?.message ? (
                <div className="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
                  {askForm.formState.errors.root.message}
                </div>
              ) : null}
              <div className="flex flex-wrap items-center gap-3">
                <Button disabled={askForm.formState.isSubmitting}>
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
              {messages.qa.citationsEmpty}
            </div>
          ) : null}
          {citations.map((citation) => (
            <div
              key={`${citation.chunk_id}-${citation.document_id}`}
              className="rounded-2xl border border-border/70 bg-white/80 p-4"
            >
              <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                <span>{messages.common.chunk(citation.chunk_id)}</span>
                <span>{messages.common.documentId(citation.document_id)}</span>
                <span>{messages.common.shortKnowledgeBaseId(citation.knowledge_base_id)}</span>
              </div>
              <p className="mt-3 text-sm leading-6 text-foreground">{citation.text}</p>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
