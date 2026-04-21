"use client";

import { TeamCard } from "@/components/teams/team-card";
import { CreateTeamForm } from "@/components/teams/create-team-form";
import { JoinTeamForm } from "@/components/teams/join-team-form";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/hooks/use-auth";
import { useI18n } from "@/hooks/use-i18n";
import { useCreateTeam, useJoinTeam, useTeams } from "@/hooks/use-teams";

export default function TeamsPage() {
  const { accessToken } = useAuth();
  const { messages } = useI18n();
  const teamsQuery = useTeams(accessToken);
  const createTeamMutation = useCreateTeam(accessToken);
  const joinTeamMutation = useJoinTeam(accessToken);

  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-[360px_360px_minmax(0,1fr)]">
        <CreateTeamForm
          onSubmit={async (values) => {
            await createTeamMutation.mutateAsync(values);
          }}
          isSubmitting={createTeamMutation.isPending}
        />
        <JoinTeamForm
          onSubmit={async (values) => {
            await joinTeamMutation.mutateAsync(values);
          }}
          isSubmitting={joinTeamMutation.isPending}
        />
        <Card>
          <CardHeader>
            <CardTitle>{messages.teams.pageTitle}</CardTitle>
            <CardDescription>{messages.teams.pageDescription}</CardDescription>
          </CardHeader>
          <CardContent>
            {teamsQuery.isLoading ? (
              <p className="text-sm text-muted-foreground">{messages.teams.pageLoading}</p>
            ) : null}
            {teamsQuery.error ? (
              <div className="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
                {teamsQuery.error instanceof Error ? teamsQuery.error.message : messages.teams.pageLoadError}
              </div>
            ) : null}
            <div className="grid gap-4 lg:grid-cols-2">
              {(teamsQuery.data ?? []).map((team) => (
                <TeamCard key={team.id} team={team} />
              ))}
            </div>
            {teamsQuery.data?.length === 0 ? (
              <div className="rounded-3xl bg-secondary/60 p-6 text-sm text-muted-foreground">
                {messages.teams.pageEmpty}
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
