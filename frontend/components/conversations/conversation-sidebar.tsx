"use client";

import Link from "next/link";
import { MessagesSquare, Plus } from "lucide-react";

import { buttonVariants } from "@/components/ui/button";
import { useI18n } from "@/hooks/use-i18n";
import { cn, formatDate } from "@/lib/utils";
import type { ConversationSummary } from "@/types";

export function ConversationSidebar({
  conversations,
  activeConversationId
}: {
  conversations: ConversationSummary[];
  activeConversationId?: number;
}) {
  const { messages } = useI18n();

  return (
    <aside className="flex h-full flex-col gap-4 rounded-3xl border border-border/50 bg-white/70 p-3 shadow-soft backdrop-blur">
      <div className="px-1">
        <p className="text-sm font-semibold text-foreground">PureLink</p>
      </div>
      <Link
        href="/conversations/new"
        className={cn(buttonVariants({ size: "sm" }), "h-10 w-full rounded-2xl")}
      >
        <Plus className="h-4 w-4" />
        {messages.conversations.newConversation}
      </Link>

      <div className="space-y-2">
        <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
          {messages.conversations.recentTitle}
        </p>
        <div className="space-y-1.5">
          {conversations.length === 0 ? (
            <div className="rounded-2xl bg-secondary/50 p-3 text-sm text-muted-foreground">
              {messages.conversations.emptyBody}
            </div>
          ) : (
            conversations.map((conversation) => {
              const isActive = conversation.id === activeConversationId;

              return (
                <Link
                  key={conversation.id}
                  href={`/conversations/${conversation.id}`}
                  className={cn(
                    "block rounded-xl border-l-2 px-3 py-2.5 transition-colors",
                    isActive
                      ? "border-l-primary bg-primary/5"
                      : "border-l-transparent bg-transparent hover:bg-accent/70"
                  )}
                >
                  <div className="flex min-w-0 items-start gap-2.5">
                    <MessagesSquare className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                    <div className="min-w-0 space-y-1">
                      <p className="truncate text-sm font-medium text-foreground">
                        {conversation.title}
                      </p>
                      <p className="truncate text-xs text-muted-foreground">
                        {messages.common.shortKnowledgeBaseId(conversation.knowledge_base_id)} ·{" "}
                        {formatDate(conversation.updated_at)}
                      </p>
                    </div>
                  </div>
                </Link>
              );
            })
          )}
        </div>
      </div>
    </aside>
  );
}
