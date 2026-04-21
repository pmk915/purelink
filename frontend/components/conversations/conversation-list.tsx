"use client";

import Link from "next/link";
import { ArrowRight, MessagesSquare } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useI18n } from "@/hooks/use-i18n";
import type { ConversationSummary } from "@/types";
import { formatDate } from "@/lib/utils";

export function ConversationList({
  conversations
}: {
  conversations: ConversationSummary[];
}) {
  const { messages } = useI18n();

  if (conversations.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{messages.conversations.emptyTitle}</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          {messages.conversations.emptyBody}
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="grid gap-4">
      {conversations.map((conversation) => (
        <Card key={conversation.id}>
          <CardContent className="flex flex-col gap-4 pt-6 md:flex-row md:items-center md:justify-between">
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <MessagesSquare className="h-4 w-4 text-primary" />
                <h3 className="font-semibold">{conversation.title}</h3>
                <Badge variant={conversation.scope === "team" ? "secondary" : "default"}>
                  {conversation.scope === "team" ? messages.common.team : messages.common.personal}
                </Badge>
              </div>
              <p className="text-sm text-muted-foreground">
                {messages.common.knowledgeBaseId(conversation.knowledge_base_id)} ·{" "}
                {messages.common.updatedAt} {formatDate(conversation.updated_at)}
              </p>
            </div>
            <Link
              href={`/conversations/${conversation.id}`}
              className="inline-flex items-center gap-2 text-sm font-medium text-primary"
            >
              {messages.conversations.openConversation}
              <ArrowRight className="h-4 w-4" />
            </Link>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
