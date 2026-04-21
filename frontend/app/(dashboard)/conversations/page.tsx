"use client";

import { ConversationList } from "@/components/conversations/conversation-list";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/hooks/use-auth";
import { useConversations } from "@/hooks/use-conversations";
import { useI18n } from "@/hooks/use-i18n";

export default function ConversationsPage() {
  const { accessToken } = useAuth();
  const { messages } = useI18n();
  const conversationsQuery = useConversations(accessToken);

  return (
    <div className="space-y-6">
      <Card className="bg-gradient-to-br from-white via-indigo-50 to-sky-50">
        <CardHeader>
          <CardDescription>{messages.conversations.pageLabel}</CardDescription>
          <CardTitle className="text-3xl">{messages.conversations.pageTitle}</CardTitle>
        </CardHeader>
        <CardContent className="text-sm leading-7 text-muted-foreground">
          {messages.conversations.pageDescription}
        </CardContent>
      </Card>
      {conversationsQuery.data ? <ConversationList conversations={conversationsQuery.data} /> : null}
      {conversationsQuery.isLoading ? (
        <p className="text-sm text-muted-foreground">{messages.conversations.loading}</p>
      ) : null}
    </div>
  );
}
