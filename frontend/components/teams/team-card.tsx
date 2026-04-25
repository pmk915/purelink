"use client";

import Link from "next/link";
import { ArrowRight, Shield, Users } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useI18n } from "@/hooks/use-i18n";
import type { Team } from "@/types";
import { formatDate } from "@/lib/utils";

export function TeamCard({ team }: { team: Team }) {
  const { messages } = useI18n();

  return (
    <Card className="h-full transition-transform hover:-translate-y-1">
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div>
            <CardTitle>{team.name}</CardTitle>
            <CardDescription className="mt-2 line-clamp-2 min-h-[40px]">
              {team.description ?? messages.common.noDescription}
            </CardDescription>
          </div>
          <Badge variant={team.my_role === "admin" ? "default" : "secondary"}>
            {team.my_role === "admin" ? (
              <span className="inline-flex items-center gap-1">
                <Shield className="h-3.5 w-3.5" />
                {messages.common.admin}
              </span>
            ) : (
              <span className="inline-flex items-center gap-1">
                <Users className="h-3.5 w-3.5" />
                {messages.common.member}
              </span>
            )}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="text-sm text-muted-foreground">
          <p>{messages.common.teamId(team.id)}</p>
          <p>
            {messages.common.updatedAt} {formatDate(team.updated_at)}
          </p>
        </div>
        <Link
          href={`/teams/${team.id}`}
          className={buttonVariants({
            variant: "outline",
            size: "sm",
            className: "w-fit rounded-xl"
          })}
        >
          {messages.teams.openTeam}
          <ArrowRight className="h-4 w-4" />
        </Link>
      </CardContent>
    </Card>
  );
}
