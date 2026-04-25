"use client";

import Link from "next/link";
import { ShieldCheck, UserRoundPlus } from "lucide-react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { KnowledgeBaseCard } from "@/components/knowledge-bases/knowledge-base-card";
import { CreateKnowledgeBaseForm } from "@/components/knowledge-bases/create-knowledge-base-form";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/hooks/use-auth";
import { useI18n } from "@/hooks/use-i18n";
import {
  useCreateTeamKnowledgeBase,
  useTeamsKnowledgeBases
} from "@/hooks/use-knowledge-bases";
import { useTeamReviewTasks } from "@/hooks/use-documents";
import { useCreateTeamInvite, useTeam, useTeamInvites, useTeamMembers } from "@/hooks/use-teams";
import { createInviteSchema, type CreateInviteValues } from "@/schemas/teams";
import { formatDate } from "@/lib/utils";

export default function TeamDetailPage({
  params
}: {
  params: { teamId: string };
}) {
  const teamId = Number(params.teamId);
  const { accessToken } = useAuth();
  const { messages } = useI18n();
  const teamQuery = useTeam(accessToken, teamId);
  const membersQuery = useTeamMembers(accessToken, teamId);
  const invitesQuery = useTeamInvites(accessToken, teamId);
  const teamKnowledgeBasesQuery = useTeamsKnowledgeBases(accessToken, teamId);
  const createInviteMutation = useCreateTeamInvite(accessToken, teamId);
  const createTeamKbMutation = useCreateTeamKnowledgeBase(accessToken, teamId);

  const inviteForm = useForm<CreateInviteValues>({
    resolver: zodResolver(createInviteSchema),
    defaultValues: { expires_in_days: 7 }
  });

  const team = teamQuery.data;
  const isAdmin = team?.my_role === "admin";
  const reviewTasksQuery = useTeamReviewTasks(isAdmin ? accessToken : null, teamId);
  const pendingReviewCount = reviewTasksQuery.data?.length ?? 0;
  const activeInvites = (invitesQuery.data ?? []).filter(
    (invite) =>
      invite.status === "active" &&
      new Date(invite.expires_at).getTime() > Date.now()
  );

  return (
    <div className="space-y-6">
      <Card className="bg-gradient-to-br from-white via-indigo-50 to-sky-50">
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <CardDescription>{messages.teams.detailLabel}</CardDescription>
              <CardTitle className="mt-2 text-3xl">
                {team?.name ?? messages.teams.loadingTeam}
              </CardTitle>
              <CardDescription className="mt-4 max-w-3xl text-base leading-7">
                {team?.description ?? messages.common.noDescription}
              </CardDescription>
            </div>
            {team ? (
              <Badge variant={team.my_role === "admin" ? "default" : "secondary"}>
                {team.my_role === "admin" ? messages.common.admin : messages.common.member}
              </Badge>
            ) : null}
          </div>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-4 text-sm text-muted-foreground">
          <span>{messages.common.teamId(teamId)}</span>
          {team ? <span>{messages.common.updatedAt} {formatDate(team.updated_at)}</span> : null}
        </CardContent>
      </Card>

      {isAdmin ? (
        <Card className="border-amber-200 bg-amber-50/70">
          <CardContent className="flex flex-wrap items-center justify-between gap-4 pt-6">
            <div>
              <p className="font-medium text-foreground">{messages.teams.reviewSummaryTitle}</p>
              <p className="mt-1 text-sm text-muted-foreground">
                {messages.teams.reviewSummaryDescription(pendingReviewCount)}
              </p>
            </div>
            <Link href={`/teams/${teamId}/reviews`}>
              <Button variant={pendingReviewCount > 0 ? "default" : "outline"}>
                {messages.teams.reviewsLink}
              </Button>
            </Link>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Card>
          <CardHeader>
            <CardTitle>{messages.teams.teamKnowledgeBasesTitle}</CardTitle>
            <CardDescription>{messages.teams.teamKnowledgeBasesDescription}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 lg:grid-cols-2">
              {(teamKnowledgeBasesQuery.data ?? []).map((knowledgeBase) => (
                <KnowledgeBaseCard
                  key={knowledgeBase.id}
                  knowledgeBase={knowledgeBase}
                  href={`/teams/${teamId}/knowledge-bases/${knowledgeBase.id}`}
                />
              ))}
            </div>
            {teamKnowledgeBasesQuery.data?.length === 0 ? (
              <div className="rounded-3xl bg-secondary/60 p-6 text-sm text-muted-foreground">
                {messages.teams.teamKnowledgeBasesEmpty}
              </div>
            ) : null}
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>{messages.teams.membersTitle}</CardTitle>
              <CardDescription>{messages.teams.membersDescription}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {(membersQuery.data ?? []).map((member) => (
                <div
                  key={member.id}
                  className="rounded-2xl border border-border/70 bg-white/80 p-4"
                >
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <p className="font-medium text-foreground">{member.user.username}</p>
                      <p className="text-sm text-muted-foreground">{member.user.email}</p>
                    </div>
                    <Badge variant={member.role === "admin" ? "default" : "secondary"}>
                      {member.role === "admin" ? messages.common.admin : messages.common.member}
                    </Badge>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          {isAdmin ? (
            <CreateKnowledgeBaseForm
              title={messages.teams.createKbTitle}
              description={messages.teams.createKbDescription}
              submitLabel={messages.common.create}
              onSubmit={async (values) => {
                await createTeamKbMutation.mutateAsync(values);
              }}
              isSubmitting={createTeamKbMutation.isPending}
            />
          ) : null}

          {isAdmin ? (
            <Card>
              <CardHeader>
                <CardTitle>{messages.teams.inviteTitle}</CardTitle>
                <CardDescription>{messages.teams.inviteDescription}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <form
                  className="space-y-4"
                  onSubmit={inviteForm.handleSubmit(async (values) => {
                    try {
                      await createInviteMutation.mutateAsync(values);
                    } catch (error) {
                      inviteForm.setError("root", {
                        message:
                          error instanceof Error ? error.message : messages.teams.inviteError
                      });
                    }
                  })}
                >
                  <div className="space-y-2">
                    <Label htmlFor="expires-in-days">{messages.teams.expiresInDays}</Label>
                    <Input
                      id="expires-in-days"
                      type="number"
                      min={1}
                      max={365}
                      {...inviteForm.register("expires_in_days", {
                        valueAsNumber: true
                      })}
                    />
                  </div>
                  {inviteForm.formState.errors.root?.message ? (
                    <div className="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
                      {inviteForm.formState.errors.root.message}
                    </div>
                  ) : null}
                  <Button disabled={createInviteMutation.isPending}>
                    <UserRoundPlus className="h-4 w-4" />
                    {createInviteMutation.isPending
                      ? messages.teams.creating
                      : messages.common.createInvite}
                  </Button>
                </form>

                <div className="space-y-3">
                  {activeInvites.map((invite) => (
                    <div key={invite.id} className="rounded-2xl bg-secondary/60 p-4">
                      <div className="flex items-center justify-between gap-4">
                        <code className="font-mono text-sm text-foreground">{invite.code}</code>
                        <Badge variant={invite.status === "active" ? "success" : "outline"}>
                          {invite.status}
                        </Badge>
                      </div>
                      <p className="mt-2 text-xs text-muted-foreground">
                        {messages.common.expires} {formatDate(invite.expires_at)}
                      </p>
                    </div>
                  ))}
                  {activeInvites.length === 0 ? (
                    <p className="rounded-2xl bg-secondary/60 p-4 text-sm text-muted-foreground">
                      {messages.teams.inviteEmpty}
                    </p>
                  ) : null}
                </div>
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardHeader>
                <CardTitle>{messages.teams.permissionsTitle}</CardTitle>
              </CardHeader>
              <CardContent className="rounded-b-[28px] bg-secondary/60 text-sm text-muted-foreground">
                <div className="flex items-start gap-3">
                  <ShieldCheck className="mt-0.5 h-4 w-4 text-primary" />
                  <p>{messages.teams.permissionsBody}</p>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
