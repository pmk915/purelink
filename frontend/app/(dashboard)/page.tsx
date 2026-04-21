"use client";

import Link from "next/link";
import { ArrowRight, BotMessageSquare, Database, FolderPlus, Users } from "lucide-react";

import { ConversationList } from "@/components/conversations/conversation-list";
import { KnowledgeBaseCard } from "@/components/knowledge-bases/knowledge-base-card";
import { TeamCard } from "@/components/teams/team-card";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/hooks/use-auth";
import { useConversations } from "@/hooks/use-conversations";
import { useI18n } from "@/hooks/use-i18n";
import { usePersonalKnowledgeBases } from "@/hooks/use-knowledge-bases";
import { useTeams } from "@/hooks/use-teams";

export default function DashboardPage() {
  const { accessToken, currentUser } = useAuth();
  const { messages } = useI18n();
  const kbQuery = usePersonalKnowledgeBases(accessToken);
  const teamsQuery = useTeams(accessToken);
  const conversationsQuery = useConversations(accessToken);
  const recentKnowledgeBases = (kbQuery.data ?? []).slice(0, 3);
  const recentTeams = (teamsQuery.data ?? []).slice(0, 2);
  const recentConversations = (conversationsQuery.data ?? []).slice(0, 3);

  const stats = [
    {
      label: messages.dashboard.stats.personalKnowledgeBases,
      value: kbQuery.data?.length ?? 0,
      icon: Database
    },
    {
      label: messages.dashboard.stats.teams,
      value: teamsQuery.data?.length ?? 0,
      icon: Users
    },
    {
      label: messages.dashboard.stats.conversations,
      value: conversationsQuery.data?.length ?? 0,
      icon: BotMessageSquare
    }
  ];

  return (
    <div className="space-y-6">
      <Card className="overflow-hidden bg-gradient-to-br from-white via-indigo-50 to-sky-50">
        <CardHeader className="pb-4">
          <CardDescription>{messages.dashboard.label}</CardDescription>
          <CardTitle className="text-3xl">
            {messages.dashboard.welcome(currentUser?.username ?? messages.common.anonymous)}
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-8 lg:grid-cols-[minmax(0,1.1fr)_360px]">
          <div className="space-y-5">
            <p className="max-w-3xl text-base leading-8 text-muted-foreground">
              {messages.dashboard.intro}
            </p>
            <div className="flex flex-wrap gap-3">
              <Link
                href="/knowledge-bases"
                className="inline-flex items-center gap-2 rounded-2xl bg-primary px-4 py-3 text-sm font-medium text-primary-foreground shadow-soft"
              >
                {messages.dashboard.openKnowledgeBases}
                <ArrowRight className="h-4 w-4" />
              </Link>
              <Link
                href="/teams"
                className="inline-flex items-center gap-2 rounded-2xl border border-border/70 bg-white/70 px-4 py-3 text-sm font-medium text-foreground"
              >
                {messages.dashboard.openTeams}
              </Link>
              <Link
                href="/conversations"
                className="inline-flex items-center gap-2 rounded-2xl border border-border/70 bg-white/70 px-4 py-3 text-sm font-medium text-foreground"
              >
                {messages.dashboard.openConversations}
              </Link>
            </div>
          </div>
          <div className="rounded-[28px] border border-white/60 bg-white/80 p-6 shadow-card">
            <p className="text-sm font-medium text-foreground">
              {messages.dashboard.quickActionsTitle}
            </p>
            <p className="mt-2 text-sm leading-7 text-muted-foreground">
              {messages.dashboard.quickActionsDescription}
            </p>
            <div className="mt-5 space-y-3">
              <Link
                href="/knowledge-bases"
                className="flex items-start gap-3 rounded-2xl border border-border/70 bg-background/70 p-4 transition hover:bg-background"
              >
                <div className="mt-0.5 rounded-xl bg-primary/10 p-2 text-primary">
                  <FolderPlus className="h-4 w-4" />
                </div>
                <div>
                  <p className="font-medium text-foreground">{messages.dashboard.newKnowledgeBase}</p>
                  <p className="mt-1 text-sm leading-6 text-muted-foreground">
                    {messages.dashboard.quickActionKnowledgeBases}
                  </p>
                </div>
              </Link>
              <Link
                href="/teams"
                className="flex items-start gap-3 rounded-2xl border border-border/70 bg-background/70 p-4 transition hover:bg-background"
              >
                <div className="mt-0.5 rounded-xl bg-primary/10 p-2 text-primary">
                  <Users className="h-4 w-4" />
                </div>
                <div>
                  <p className="font-medium text-foreground">{messages.dashboard.openTeams}</p>
                  <p className="mt-1 text-sm leading-6 text-muted-foreground">
                    {messages.dashboard.quickActionTeams}
                  </p>
                </div>
              </Link>
              <Link
                href="/conversations"
                className="flex items-start gap-3 rounded-2xl border border-border/70 bg-background/70 p-4 transition hover:bg-background"
              >
                <div className="mt-0.5 rounded-xl bg-primary/10 p-2 text-primary">
                  <BotMessageSquare className="h-4 w-4" />
                </div>
                <div>
                  <p className="font-medium text-foreground">{messages.dashboard.openConversations}</p>
                  <p className="mt-1 text-sm leading-6 text-muted-foreground">
                    {messages.dashboard.quickActionConversations}
                  </p>
                </div>
              </Link>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-3">
        {stats.map((item) => {
          const Icon = item.icon;
          return (
            <Card key={item.label}>
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  <p className="text-sm text-muted-foreground">{item.label}</p>
                  <p className="mt-3 text-3xl font-semibold tracking-tight">{item.value}</p>
                </div>
                <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                  <Icon className="h-6 w-6" />
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
        <Card>
          <CardHeader>
            <CardTitle>{messages.dashboard.recentKnowledgeBasesTitle}</CardTitle>
            <CardDescription>{messages.dashboard.recentKnowledgeBasesDescription}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {recentKnowledgeBases.length === 0 ? (
              <div className="rounded-3xl bg-secondary/60 p-6 text-sm text-muted-foreground">
                {messages.dashboard.recentKnowledgeBasesEmpty}
              </div>
            ) : (
              <div className="grid gap-4 lg:grid-cols-2">
                {recentKnowledgeBases.map((knowledgeBase) => (
                  <KnowledgeBaseCard
                    key={knowledgeBase.id}
                    knowledgeBase={knowledgeBase}
                    href={`/knowledge-bases/${knowledgeBase.id}`}
                  />
                ))}
              </div>
            )}
            <Link
              href="/knowledge-bases"
              className="inline-flex items-center gap-2 text-sm font-medium text-primary"
            >
              {messages.dashboard.managePersonal}
              <ArrowRight className="h-4 w-4" />
            </Link>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{messages.dashboard.recentConversationsTitle}</CardTitle>
            <CardDescription>{messages.dashboard.recentConversationsDescription}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {recentConversations.length === 0 ? (
              <div className="rounded-3xl bg-secondary/60 p-6 text-sm text-muted-foreground">
                {messages.dashboard.recentConversationsEmpty}
              </div>
            ) : (
              <ConversationList conversations={recentConversations} />
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{messages.dashboard.recentTeamsTitle}</CardTitle>
          <CardDescription>{messages.dashboard.recentTeamsDescription}</CardDescription>
        </CardHeader>
        <CardContent>
          {recentTeams.length === 0 ? (
            <div className="rounded-3xl bg-secondary/60 p-6 text-sm text-muted-foreground">
              {messages.dashboard.recentTeamsEmpty}
            </div>
          ) : (
            <div className="grid gap-4 lg:grid-cols-2">
              {recentTeams.map((team) => (
                <TeamCard key={team.id} team={team} />
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
