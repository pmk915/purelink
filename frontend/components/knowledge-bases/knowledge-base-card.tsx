"use client";

import Link from "next/link";
import { ArrowRight, Database, Trash2, Users } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useI18n } from "@/hooks/use-i18n";
import type { KnowledgeBase } from "@/types";
import { formatDate } from "@/lib/utils";

export function KnowledgeBaseCard({
  knowledgeBase,
  href,
  onDelete,
  canDelete = false,
  deleteDisabledReason
}: {
  knowledgeBase: KnowledgeBase;
  href: string;
  onDelete?: () => void;
  canDelete?: boolean;
  deleteDisabledReason?: string | null;
}) {
  const { messages } = useI18n();
  return (
    <Card className="h-full transition-transform hover:-translate-y-1">
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div>
            <CardTitle>{knowledgeBase.name}</CardTitle>
            <CardDescription className="mt-2 line-clamp-2 min-h-[40px]">
              {knowledgeBase.description ?? messages.common.noDescriptionProvided}
            </CardDescription>
          </div>
          <Badge variant={knowledgeBase.scope === "team" ? "secondary" : "default"}>
            {knowledgeBase.scope === "team" ? (
              <span className="inline-flex items-center gap-1">
                <Users className="h-3.5 w-3.5" />
                {messages.common.team}
              </span>
            ) : (
              <span className="inline-flex items-center gap-1">
                <Database className="h-3.5 w-3.5" />
                {messages.common.personal}
              </span>
            )}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid gap-2 text-sm text-muted-foreground">
          <p>
            {messages.common.updatedAt} {formatDate(knowledgeBase.updated_at)}
          </p>
          <p>{messages.common.knowledgeBaseId(knowledgeBase.id)}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            href={href}
            className={buttonVariants({
              variant: "outline",
              size: "sm",
              className: "w-fit rounded-xl"
            })}
          >
            {messages.knowledgeBases.openWorkspace}
            <ArrowRight className="h-4 w-4" />
          </Link>
          {onDelete || deleteDisabledReason ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="rounded-xl text-rose-600 hover:bg-rose-50 hover:text-rose-700"
              disabled={!canDelete}
              title={!canDelete ? deleteDisabledReason ?? undefined : undefined}
              onClick={canDelete ? onDelete : undefined}
            >
              <Trash2 className="h-4 w-4" />
              {messages.common.delete}
            </Button>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
