"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ChevronDown, ChevronUp, Sparkles } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { ConversationSidebar } from "@/components/conversations/conversation-sidebar";
import { CitationAwareAnswer } from "@/components/qa/citation-aware-answer";
import { CitationCard } from "@/components/qa/citation-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/hooks/use-auth";
import { usePersonalDocuments, useTeamDocuments } from "@/hooks/use-documents";
import {
  useAppendConversationMessage,
  useConversation,
  useConversations
} from "@/hooks/use-conversations";
import { useI18n } from "@/hooks/use-i18n";
import { usePersonalKnowledgeBase, useTeamKnowledgeBase } from "@/hooks/use-knowledge-bases";
import { useTeam } from "@/hooks/use-teams";
import { formatDate } from "@/lib/utils";
import type { Document } from "@/types";
import { askSchema, type AskValues } from "@/schemas/qa";

function isDocumentQueryable(document: Document) {
  return (
    document.review_status !== "pending_review" &&
    document.review_status !== "rejected" &&
    document.processing_status === "indexed"
  );
}

function isDocumentPreparing(document: Document) {
  if (
    document.review_status === "pending_review" ||
    document.review_status === "rejected"
  ) {
    return false;
  }

  return (
    document.processing_status === "uploaded" ||
    document.processing_status === "processing" ||
    document.processing_status === "parsed" ||
    document.latest_processing_job_status === "queued" ||
    document.latest_processing_job_status === "processing" ||
    document.latest_processing_job_status === "retrying"
  );
}

function needsKnowledgeBaseReindex(document: Document) {
  return document.latest_processing_job_error_code === "DOCUMENT_INDEXING_FAILED";
}

export default function ConversationDetailPage({
  params
}: {
  params: { conversationId: string };
}) {
  const conversationId = Number(params.conversationId);
  const { accessToken } = useAuth();
  const { messages } = useI18n();
  const [expandedSourceMessageIds, setExpandedSourceMessageIds] = useState<number[]>([]);
  const conversationsQuery = useConversations(accessToken);
  const conversationQuery = useConversation(accessToken, conversationId);
  const conversation = conversationQuery.data;

  const personalKbQuery = usePersonalKnowledgeBase(
    accessToken,
    conversation?.scope === "personal" ? conversation.knowledge_base_id : Number.NaN
  );
  const teamKbQuery = useTeamKnowledgeBase(
    accessToken,
    conversation?.scope === "team" ? conversation.team_id ?? Number.NaN : Number.NaN,
    conversation?.scope === "team" ? conversation.knowledge_base_id : Number.NaN
  );
  const teamQuery = useTeam(
    conversation?.scope === "team" ? accessToken : null,
    conversation?.team_id ?? Number.NaN
  );
  const personalDocumentsQuery = usePersonalDocuments(
    accessToken,
    conversation?.scope === "personal" ? conversation.knowledge_base_id : Number.NaN
  );
  const teamDocumentsQuery = useTeamDocuments(
    accessToken,
    conversation?.scope === "team" ? conversation.team_id ?? Number.NaN : Number.NaN,
    conversation?.scope === "team" ? conversation.knowledge_base_id : Number.NaN
  );
  const appendMessage = useAppendConversationMessage(accessToken, conversationId);

  const askForm = useForm<AskValues>({
    resolver: zodResolver(askSchema),
    defaultValues: {
      question: "",
      top_k: 5,
      conversation_id: conversationId
    }
  });

  if (conversationQuery.isLoading) {
    return <p className="text-sm text-muted-foreground">{messages.conversations.loadingSingle}</p>;
  }

  if (!conversation) {
    return (
      <div className="rounded-3xl border border-border/70 bg-white/80 p-6 shadow-card">
        <p className="text-lg font-semibold text-foreground">{messages.conversations.notFound}</p>
      </div>
    );
  }

  const knowledgeBase =
    conversation.scope === "team" ? teamKbQuery.data : personalKbQuery.data;
  const documents =
    conversation.scope === "team"
      ? teamDocumentsQuery.data ?? []
      : personalDocumentsQuery.data ?? [];
  const documentsLoading =
    conversation.scope === "team"
      ? teamDocumentsQuery.isLoading
      : personalDocumentsQuery.isLoading;
  const hasQueryableDocuments = documents.some(isDocumentQueryable);
  const hasPendingReviewDocuments = documents.some(
    (document) => document.review_status === "pending_review"
  );
  const hasPreparingDocuments = documents.some(isDocumentPreparing);
  const hasReadyButUnindexedDocuments = documents.some(
    (document) => document.processing_status === "ready"
  );
  const hasReindexRequiredDocuments = documents.some(needsKnowledgeBaseReindex);
  const blockingAvailabilityMessage = documentsLoading
    ? null
    : documents.length === 0
      ? conversation.scope === "personal"
        ? messages.qa.noQueryablePersonalKnowledgeBase
        : messages.qa.noQueryableTeamKnowledgeBase
      : !hasQueryableDocuments && hasPendingReviewDocuments
        ? messages.qa.documentsWaitingReview
        : !hasQueryableDocuments && hasPreparingDocuments
          ? messages.qa.documentsPreparing
          : !hasQueryableDocuments && hasReadyButUnindexedDocuments
            ? messages.qa.documentsReadyButNotIndexed
            : !hasQueryableDocuments
              ? conversation.scope === "personal"
                ? messages.qa.noQueryablePersonalKnowledgeBase
                : messages.qa.noQueryableTeamKnowledgeBase
              : null;
  const warningAvailabilityMessage =
    !documentsLoading && hasReindexRequiredDocuments ? messages.qa.documentsNeedReindex : null;
  const canAppendMessage =
    appendMessage.isPending || askForm.formState.isSubmitting ? false : !blockingAvailabilityMessage;
  const toggleSources = (messageId: number) => {
    setExpandedSourceMessageIds((current) =>
      current.includes(messageId)
        ? current.filter((id) => id !== messageId)
        : [...current, messageId]
    );
  };

  return (
    <div
      data-testid="conversation-thread-page"
      className="grid h-[calc(100vh-8rem)] min-h-0 gap-4 overflow-hidden md:h-[calc(100vh-9rem)] xl:grid-cols-[280px_minmax(0,1fr)]"
    >
      <div className="hidden h-full min-h-0 xl:block">
        <ConversationSidebar
          conversations={conversationsQuery.data ?? []}
          activeConversationId={conversationId}
        />
      </div>

      <section className="flex h-full min-h-0 flex-col overflow-hidden rounded-[28px] border border-border/50 bg-white/75 shadow-soft backdrop-blur">
        <header className="shrink-0 border-b border-border/50 px-5 py-3 sm:px-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <h1 className="truncate text-sm font-semibold text-foreground">
                {knowledgeBase?.name ?? messages.common.knowledgeBaseId(conversation.knowledge_base_id)}
              </h1>
              <p className="truncate text-xs text-muted-foreground">
                {messages.conversations.currentKnowledgeBase} ·{" "}
                {conversation.scope === "team"
                  ? `${messages.common.team} · ${teamQuery.data?.name ?? messages.common.teamId(conversation.team_id ?? 0)}`
                  : messages.knowledgeBases.workspaceScopePersonal}{" "}
                · {messages.common.updatedAt} {formatDate(conversation.updated_at)}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Badge variant={conversation.scope === "team" ? "secondary" : "default"}>
                {conversation.scope === "team" ? messages.common.team : messages.common.personal}
              </Badge>
            </div>
          </div>
        </header>

        <div
          data-testid="conversation-message-list-scroller"
          className="min-h-0 flex-1 overflow-y-auto px-4 py-6 sm:px-6"
        >
          <div
            data-testid="conversation-message-list"
            className="mx-auto flex w-full max-w-3xl min-w-0 flex-col gap-8"
          >
            {conversation.messages.length === 0 ? (
              <div className="flex min-h-[40vh] flex-col items-center justify-center gap-3 text-center">
                <p className="text-2xl font-semibold text-foreground">
                  {messages.conversations.readyWhenYouAre}
                </p>
                <p className="text-sm text-muted-foreground">{messages.conversations.noMessagesYet}</p>
              </div>
            ) : null}

            {conversation.messages.map((message) => {
              const isAssistant = message.role === "assistant";
              const sourcesExpanded = expandedSourceMessageIds.includes(message.id);

              return (
                <div
                  key={message.id}
                  className="space-y-3"
                  data-testid="conversation-message-item"
                  data-message-role={message.role}
                  data-message-id={message.id}
                >
                  <div className={isAssistant ? "flex justify-start" : "flex justify-end"}>
                    <div className={isAssistant ? "max-w-[880px]" : "max-w-[75%]"}>
                      {isAssistant ? (
                        <div className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-primary">
                          PureLink
                        </div>
                      ) : null}
                      <div
                        className={
                          isAssistant
                            ? "px-1 text-sm leading-7 text-foreground break-words [overflow-wrap:anywhere]"
                            : "rounded-3xl bg-secondary/80 px-4 py-3 text-sm leading-7 text-foreground break-words [overflow-wrap:anywhere]"
                        }
                      >
                        {isAssistant ? (
                          <CitationAwareAnswer
                            answer={message.content}
                            citations={message.citations}
                          />
                        ) : (
                          <p className="whitespace-pre-wrap">{message.content}</p>
                        )}
                      </div>
                      <div
                        className={
                          isAssistant
                            ? "mt-2 px-1 text-xs text-muted-foreground"
                            : "mt-2 px-1 text-right text-xs text-muted-foreground"
                        }
                      >
                        {formatDate(message.created_at)}
                      </div>
                    </div>
                  </div>

                  {isAssistant && message.citations.length > 0 ? (
                    <div className="max-w-[880px] min-w-0 pl-1">
                      <button
                        type="button"
                        data-testid={`conversation-sources-toggle-${message.id}`}
                        className="inline-flex items-center gap-2 rounded-full bg-secondary/60 px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                        onClick={() => toggleSources(message.id)}
                      >
                        {sourcesExpanded ? (
                          <ChevronUp className="h-3.5 w-3.5" />
                        ) : (
                          <ChevronDown className="h-3.5 w-3.5" />
                        )}
                        {sourcesExpanded
                          ? messages.conversations.hideSources(message.citations.length)
                          : messages.conversations.viewSources(message.citations.length)}
                      </button>

                      {sourcesExpanded ? (
                        <div className="mt-3 grid max-h-80 gap-2.5 overflow-y-auto pr-1">
                          <details className="rounded-2xl border border-border/60 bg-secondary/40 px-3.5 py-3 text-xs text-muted-foreground">
                            <summary className="cursor-pointer font-medium text-foreground">
                              {messages.qa.retrievalDetails}
                            </summary>
                            <div className="mt-2 space-y-1">
                              <p>{messages.qa.evidenceCount(message.citations.length)}</p>
                              <p>{messages.qa.retrievalDetailsDescription}</p>
                            </div>
                          </details>
                          {message.citations.map((citation, index) => (
                            <CitationCard
                              key={`${message.id}-${citation.citation_unit_id ?? citation.chunk_db_id ?? citation.chunk_id}-${index}`}
                              citation={citation}
                              compact
                            />
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        </div>

        <footer className="shrink-0 border-t border-border/50 bg-white/85 px-4 py-4 sm:px-6">
          <form
            className="mx-auto w-full max-w-3xl space-y-3"
            onSubmit={askForm.handleSubmit(async (values) => {
              if (blockingAvailabilityMessage) {
                return;
              }

              try {
                await appendMessage.mutateAsync({
                  content: values.question
                });

                askForm.reset({
                  question: "",
                  top_k: 5,
                  conversation_id: conversation.id
                });
                await conversationQuery.refetch();
              } catch (error) {
                console.error("ask failed", { error, conversationId: conversation.id });
                askForm.setError("root", {
                  message: messages.qa.askFailed
                });
              }
            })}
          >
            {blockingAvailabilityMessage ? (
              <div className="rounded-2xl bg-secondary/80 px-4 py-2.5 text-sm text-muted-foreground">
                {blockingAvailabilityMessage}
              </div>
            ) : null}

            {warningAvailabilityMessage ? (
              <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-800">
                {warningAvailabilityMessage}
              </div>
            ) : null}

            {askForm.formState.errors.root?.message ? (
              <div className="rounded-2xl bg-rose-50 px-4 py-2.5 text-sm text-rose-700">
                {askForm.formState.errors.root.message}
              </div>
            ) : null}

            <div className="rounded-[28px] border border-border/60 bg-background px-4 py-3 shadow-soft">
              <Textarea
                id="conversation-question"
                data-testid="conversation-question-input"
                rows={4}
                disabled={!canAppendMessage}
                placeholder={messages.qa.askPlaceholder}
                className="min-h-[64px] resize-none border-0 bg-transparent px-0 py-0 text-sm leading-6 shadow-none focus-visible:ring-0 [overflow-wrap:anywhere]"
                {...askForm.register("question")}
              />

              <div className="mt-3 flex items-center justify-between gap-4">
                <p className="text-xs text-rose-600">{askForm.formState.errors.question?.message}</p>
                <Button
                  className="rounded-2xl"
                  disabled={!canAppendMessage}
                  data-testid="conversation-question-submit"
                >
                  <Sparkles className="h-4 w-4" />
                  {askForm.formState.isSubmitting || appendMessage.isPending
                    ? messages.qa.asking
                    : messages.qa.askSubmit}
                </Button>
              </div>
            </div>
          </form>
        </footer>
      </section>
    </div>
  );
}
