"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/hooks/use-auth";
import { useConversation } from "@/hooks/use-conversations";
import { useI18n } from "@/hooks/use-i18n";
import { formatDate } from "@/lib/utils";

export default function ConversationDetailPage({
  params
}: {
  params: { conversationId: string };
}) {
  const conversationId = Number(params.conversationId);
  const { accessToken } = useAuth();
  const { messages } = useI18n();
  const conversationQuery = useConversation(accessToken, conversationId);
  const conversation = conversationQuery.data;

  if (conversationQuery.isLoading) {
    return <p className="text-sm text-muted-foreground">{messages.conversations.loadingSingle}</p>;
  }

  if (!conversation) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{messages.conversations.notFound}</CardTitle>
        </CardHeader>
      </Card>
    );
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
      <Card className="h-fit xl:sticky xl:top-28">
        <CardHeader>
          <CardDescription>{messages.conversations.summaryLabel}</CardDescription>
          <CardTitle>{conversation.title}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-muted-foreground">
          <p>{messages.common.conversationId(conversation.id)}</p>
          <p>{messages.common.knowledgeBaseId(conversation.knowledge_base_id)}</p>
          <div className="flex gap-2">
            <Badge variant={conversation.scope === "team" ? "secondary" : "default"}>
              {conversation.scope === "team" ? messages.common.team : messages.common.personal}
            </Badge>
            {conversation.team_id ? <Badge variant="outline">{messages.common.teamId(conversation.team_id)}</Badge> : null}
          </div>
          <p>{messages.common.updatedAt} {formatDate(conversation.updated_at)}</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{messages.conversations.messagesTitle}</CardTitle>
          <CardDescription>{messages.conversations.messagesDescription}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {conversation.messages.map((message) => (
            <div
              key={message.id}
              className={`rounded-3xl p-5 ${
                message.role === "assistant"
                  ? "bg-secondary/60"
                  : "border border-border/70 bg-white/80"
              }`}
            >
              <div className="flex items-center justify-between gap-4">
                <Badge variant={message.role === "assistant" ? "default" : "outline"}>
                  {message.role === "assistant" ? messages.common.assistant : messages.common.user}
                </Badge>
                <span className="text-xs text-muted-foreground">
                  {formatDate(message.created_at)}
                </span>
              </div>
              <p className="mt-4 whitespace-pre-wrap text-sm leading-7 text-foreground">
                {message.content}
              </p>
              {message.citations.length > 0 ? (
                <div className="mt-4 grid gap-3">
                  {message.citations.map((citation) => (
                    <div
                      key={`${message.id}-${citation.chunk_id}`}
                      className="rounded-2xl border border-border/70 bg-white/80 p-4"
                    >
                      <p className="text-xs text-muted-foreground">
                        {messages.common.chunk(citation.chunk_id)} ·{" "}
                        {messages.common.documentId(citation.document_id)}
                      </p>
                      <p className="mt-2 text-sm leading-6 text-foreground">{citation.text}</p>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
