"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ChevronDown, ChevronUp, Sparkles } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { ConversationSidebar } from "@/components/conversations/conversation-sidebar";
import { CitationCard } from "@/components/qa/citation-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/hooks/use-auth";
import { useConversation, useConversations } from "@/hooks/use-conversations";
import { useI18n } from "@/hooks/use-i18n";
import { usePersonalKnowledgeBase, useTeamKnowledgeBase } from "@/hooks/use-knowledge-bases";
import { useAskPersonal, useAskTeam } from "@/hooks/use-qa";
import { useTeam } from "@/hooks/use-teams";
import { formatDate } from "@/lib/utils";
import { askSchema, type AskValues } from "@/schemas/qa";

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
  const askPersonal = useAskPersonal(
    accessToken,
    conversation?.scope === "personal" ? conversation.knowledge_base_id : Number.NaN
  );
  const askTeam = useAskTeam(
    accessToken,
    conversation?.scope === "team" ? conversation.team_id ?? Number.NaN : Number.NaN,
    conversation?.scope === "team" ? conversation.knowledge_base_id : Number.NaN
  );

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
  const toggleSources = (messageId: number) => {
    setExpandedSourceMessageIds((current) =>
      current.includes(messageId)
        ? current.filter((id) => id !== messageId)
        : [...current, messageId]
    );
  };

  return (
    <div className="grid gap-4 xl:grid-cols-[280px_minmax(0,1fr)]">
      <div className="hidden xl:block xl:sticky xl:top-24 xl:h-[calc(100vh-7rem)]">
        <ConversationSidebar
          conversations={conversationsQuery.data ?? []}
          activeConversationId={conversationId}
        />
      </div>

      <section className="flex min-h-[calc(100vh-7rem)] flex-col overflow-hidden rounded-[28px] border border-border/50 bg-white/75 shadow-soft backdrop-blur">
        <header className="border-b border-border/50 px-5 py-3 sm:px-6">
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

        <div className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
          <div className="mx-auto flex w-full max-w-4xl flex-col gap-8">
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
                <div key={message.id} className="space-y-3">
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
                            ? "px-1 text-sm leading-7 text-foreground"
                            : "rounded-3xl bg-secondary/80 px-4 py-3 text-sm leading-7 text-foreground"
                        }
                      >
                        <p className="whitespace-pre-wrap">{message.content}</p>
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
                    <div className="max-w-[880px] pl-1">
                      <button
                        type="button"
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
                        <div className="mt-3 grid gap-2.5">
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

        <footer className="border-t border-border/50 bg-white/85 px-4 py-4 sm:px-6">
          <form
            className="mx-auto w-full max-w-3xl space-y-3"
            onSubmit={askForm.handleSubmit(async (values) => {
              try {
                if (conversation.scope === "team" && conversation.team_id) {
                  await askTeam.mutateAsync({
                    ...values,
                    conversation_id: conversation.id
                  });
                } else {
                  await askPersonal.mutateAsync({
                    ...values,
                    conversation_id: conversation.id
                  });
                }

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
            {askForm.formState.errors.root?.message ? (
              <div className="rounded-2xl bg-rose-50 px-4 py-2.5 text-sm text-rose-700">
                {askForm.formState.errors.root.message}
              </div>
            ) : null}

            <div className="rounded-[28px] border border-border/60 bg-background px-4 py-3 shadow-soft">
              <Textarea
                id="conversation-question"
                rows={4}
                placeholder={messages.qa.askPlaceholder}
                className="min-h-[64px] resize-none border-0 bg-transparent px-0 py-0 text-sm leading-6 shadow-none focus-visible:ring-0"
                {...askForm.register("question")}
              />

              <div className="mt-3 flex items-center justify-between gap-4">
                <p className="text-xs text-rose-600">{askForm.formState.errors.question?.message}</p>
                <Button
                  className="rounded-2xl"
                  disabled={askForm.formState.isSubmitting}
                >
                  <Sparkles className="h-4 w-4" />
                  {askForm.formState.isSubmitting ? messages.qa.asking : messages.qa.askSubmit}
                </Button>
              </div>
            </div>
          </form>
        </footer>
      </section>
    </div>
  );
}
