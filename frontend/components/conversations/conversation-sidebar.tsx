"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQueries } from "@tanstack/react-query";
import { Ellipsis, MessagesSquare, Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import * as teamsApi from "@/api/teams";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { buttonVariants } from "@/components/ui/button";
import { useAuth } from "@/hooks/use-auth";
import { useDeleteConversation } from "@/hooks/use-conversations";
import { useI18n } from "@/hooks/use-i18n";
import { usePersonalKnowledgeBases } from "@/hooks/use-knowledge-bases";
import { useTeams } from "@/hooks/use-teams";
import { cn } from "@/lib/utils";
import type { ConversationSummary } from "@/types";

export function ConversationSidebar({
  conversations,
  activeConversationId
}: {
  conversations: ConversationSummary[];
  activeConversationId?: number;
}) {
  const router = useRouter();
  const { accessToken } = useAuth();
  const { messages } = useI18n();
  const [openMenuConversationId, setOpenMenuConversationId] = useState<number | null>(null);
  const [pendingDeleteConversation, setPendingDeleteConversation] =
    useState<ConversationSummary | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const personalKnowledgeBasesQuery = usePersonalKnowledgeBases(accessToken);
  const teamsQuery = useTeams(accessToken);
  const deleteConversation = useDeleteConversation(accessToken);
  const teamKnowledgeBaseQueries = useQueries({
    queries: (teamsQuery.data ?? []).map((team) => ({
      queryKey: ["knowledge-bases", "team", team.id],
      queryFn: () => teamsApi.listTeamKnowledgeBases(accessToken as string, team.id),
      enabled: Boolean(accessToken)
    }))
  });

  const knowledgeBaseMeta = new Map<number, { name: string; scopeLabel: string }>();
  for (const knowledgeBase of personalKnowledgeBasesQuery.data ?? []) {
    knowledgeBaseMeta.set(knowledgeBase.id, {
      name: knowledgeBase.name,
      scopeLabel: messages.common.personalKnowledgeBase
    });
  }

  for (const query of teamKnowledgeBaseQueries) {
    for (const knowledgeBase of query.data ?? []) {
      knowledgeBaseMeta.set(knowledgeBase.id, {
        name: knowledgeBase.name,
        scopeLabel: messages.common.teamKnowledgeBase
      });
    }
  }

  return (
    <>
      <ConfirmDialog
        open={pendingDeleteConversation !== null}
        title={messages.conversations.deleteDialogTitle}
        description={
          pendingDeleteConversation
            ? messages.conversations.deleteDialogDescription(pendingDeleteConversation.title)
            : undefined
        }
        cancelLabel={messages.common.cancel}
        confirmLabel={
          deleteConversation.isPending ? messages.common.deleting : messages.common.delete
        }
        destructive
        loading={deleteConversation.isPending}
        onCancel={() => {
          setPendingDeleteConversation(null);
          setOpenMenuConversationId(null);
        }}
        onConfirm={async () => {
          if (!pendingDeleteConversation) {
            return;
          }

          const deletedConversationId = pendingDeleteConversation.id;
          try {
            await deleteConversation.mutateAsync(deletedConversationId);
            setDeleteError(null);
            setPendingDeleteConversation(null);
            setOpenMenuConversationId(null);
            if (deletedConversationId === activeConversationId) {
              router.push("/conversations/new");
            }
          } catch (error) {
            console.error("conversation delete failed", {
              error,
              conversationId: deletedConversationId
            });
            setDeleteError(messages.conversations.deleteFailed);
          }
        }}
      />

      <aside className="flex h-full min-h-0 flex-col gap-4 overflow-hidden rounded-3xl border border-border/50 bg-white/70 p-3 shadow-soft backdrop-blur">
      <div className="shrink-0 space-y-4">
        <div className="px-1">
          <p className="text-sm font-semibold text-foreground">PureLink</p>
        </div>
        <Link
          href="/conversations/new"
          className={cn(
            buttonVariants({ size: "sm" }),
            "flex h-10 w-full items-center justify-center gap-2 rounded-full px-4 text-sm font-medium"
          )}
        >
          <Plus className="h-4 w-4" />
          {messages.conversations.newConversation}
        </Link>

        <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
          {messages.conversations.recentTitle}
        </p>
        {deleteError ? (
          <div className="rounded-2xl bg-rose-50 px-3 py-2 text-xs text-rose-700">
            {deleteError}
          </div>
        ) : null}
      </div>

      <div className="min-h-0 flex-1 overflow-hidden">
        <div className="h-full space-y-1.5 overflow-y-auto pr-1">
          {conversations.length === 0 ? (
            <div className="rounded-2xl bg-secondary/50 p-3 text-sm text-muted-foreground">
              {messages.conversations.emptyBody}
            </div>
          ) : (
            conversations.map((conversation) => {
              const isActive = conversation.id === activeConversationId;
              const knowledgeBaseInfo = knowledgeBaseMeta.get(conversation.knowledge_base_id);
              const subtitle = knowledgeBaseInfo
                ? `${knowledgeBaseInfo.name} · ${knowledgeBaseInfo.scopeLabel}`
                : messages.common.knowledgeBaseId(conversation.knowledge_base_id);

              return (
                <div
                  key={conversation.id}
                  className={cn(
                    "group relative rounded-xl border-l-2 px-3 py-2.5 transition-colors",
                    isActive
                      ? "border-l-primary bg-primary/5"
                      : "border-l-transparent bg-transparent hover:bg-accent/70"
                  )}
                >
                  <div className="flex min-w-0 items-start gap-2.5 pr-9">
                    <MessagesSquare className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                    <Link href={`/conversations/${conversation.id}`} className="min-w-0 flex-1 space-y-1">
                      <p className="truncate text-sm font-medium text-foreground">
                        {conversation.title}
                      </p>
                      <p className="truncate text-xs text-muted-foreground">
                        {subtitle}
                      </p>
                    </Link>
                  </div>

                  <button
                    type="button"
                    aria-label={messages.conversations.moreActions}
                    className="absolute right-2 top-2 inline-flex h-7 w-7 items-center justify-center rounded-full text-muted-foreground opacity-0 transition hover:bg-background hover:text-foreground group-hover:opacity-100 focus-visible:opacity-100"
                    onClick={() => {
                      setDeleteError(null);
                      setOpenMenuConversationId((current) =>
                        current === conversation.id ? null : conversation.id
                      );
                    }}
                  >
                    <Ellipsis className="h-4 w-4" />
                  </button>

                  {openMenuConversationId === conversation.id ? (
                    <div className="absolute right-2 top-10 z-10 min-w-[140px] rounded-2xl border border-border/70 bg-white p-1.5 shadow-soft">
                      <button
                        type="button"
                        className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-sm text-rose-600 transition hover:bg-rose-50 hover:text-rose-700"
                        onClick={() => {
                          setDeleteError(null);
                          setPendingDeleteConversation(conversation);
                        }}
                      >
                        <Trash2 className="h-4 w-4" />
                        {messages.common.delete}
                      </button>
                    </div>
                  ) : null}
                </div>
              );
            })
          )}
        </div>
      </div>
      </aside>
    </>
  );
}
