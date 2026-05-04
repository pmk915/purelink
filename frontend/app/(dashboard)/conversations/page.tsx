"use client";

import Link from "next/link";

import { ConversationSidebar } from "@/components/conversations/conversation-sidebar";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/hooks/use-auth";
import { useConversations } from "@/hooks/use-conversations";
import { useI18n } from "@/hooks/use-i18n";
import { cn } from "@/lib/utils";

export default function ConversationsPage() {
  const { accessToken } = useAuth();
  const { messages } = useI18n();
  const conversationsQuery = useConversations(accessToken);

  return (
    <div className="grid gap-6 xl:grid-cols-[300px_minmax(0,1fr)]">
      <div className="xl:sticky xl:top-24 xl:h-[calc(100vh-7rem)]">
        <ConversationSidebar conversations={conversationsQuery.data ?? []} />
      </div>

      <Card className="border-border/70 shadow-card">
        <CardHeader className="space-y-3">
          <CardDescription>{messages.conversations.pageLabel}</CardDescription>
          <CardTitle className="text-3xl">{messages.conversations.pageTitle}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6 text-sm text-muted-foreground">
          <p className="leading-7">{messages.conversations.pageDescription}</p>
          <div className="rounded-3xl bg-secondary/60 p-6">
            <p className="text-base font-medium text-foreground">
              {messages.conversations.newConversationTitle}
            </p>
            <p className="mt-2 leading-7">{messages.conversations.newConversationDescription}</p>
            <div className="mt-4">
              <Link
                href="/conversations/new"
                className={cn(buttonVariants())}
              >
                {messages.conversations.newConversation}
              </Link>
            </div>
          </div>
          {conversationsQuery.isLoading ? (
            <p>{messages.conversations.loading}</p>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
