"use client";

import { Network } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/hooks/use-auth";
import { useI18n } from "@/hooks/use-i18n";
import {
  usePersonalKnowledgeGraphEntities,
  usePersonalKnowledgeGraphEntity,
  useTeamKnowledgeGraphEntities,
  useTeamKnowledgeGraphEntity
} from "@/hooks/use-knowledge-bases";
import type { KnowledgeBaseScope } from "@/types";

export function GraphExplorer({
  scope,
  knowledgeBaseId,
  teamId
}: {
  scope: KnowledgeBaseScope;
  knowledgeBaseId: number;
  teamId?: number;
}) {
  const { accessToken } = useAuth();
  const { messages } = useI18n();
  const [query, setQuery] = useState("");
  const [selectedEntityId, setSelectedEntityId] = useState<number | null>(null);
  const personalEntities = usePersonalKnowledgeGraphEntities(
    scope === "personal" ? accessToken : null,
    knowledgeBaseId,
    query
  );
  const teamEntities = useTeamKnowledgeGraphEntities(
    scope === "team" ? accessToken : null,
    teamId ?? Number.NaN,
    knowledgeBaseId,
    query
  );
  const entitiesQuery = scope === "personal" ? personalEntities : teamEntities;
  const entityItems = entitiesQuery.data?.items;
  const entities = useMemo(() => entityItems ?? [], [entityItems]);
  const firstEntityId = entities[0]?.id ?? null;
  const effectiveEntityId = useMemo(
    () =>
      selectedEntityId && entities.some((entity) => entity.id === selectedEntityId)
        ? selectedEntityId
        : firstEntityId,
    [entities, firstEntityId, selectedEntityId]
  );
  const personalDetail = usePersonalKnowledgeGraphEntity(
    scope === "personal" ? accessToken : null,
    knowledgeBaseId,
    effectiveEntityId
  );
  const teamDetail = useTeamKnowledgeGraphEntity(
    scope === "team" ? accessToken : null,
    teamId ?? Number.NaN,
    knowledgeBaseId,
    effectiveEntityId
  );
  const detail = scope === "personal" ? personalDetail.data : teamDetail.data;

  return (
    <div className="grid gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
      <Card className="border-border/70 shadow-card">
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-primary/10 text-primary">
              <Network className="h-5 w-5" />
            </div>
            <div>
              <CardTitle>{messages.graph.title}</CardTitle>
              <CardDescription>{messages.graph.description}</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={messages.graph.searchPlaceholder}
          />
          {entitiesQuery.isLoading ? (
            <p className="text-sm text-muted-foreground">{messages.common.loading}</p>
          ) : null}
          {entities.length === 0 && !entitiesQuery.isLoading ? (
            <div className="rounded-2xl bg-secondary/70 px-4 py-3 text-sm text-muted-foreground">
              {messages.graph.empty}
            </div>
          ) : (
            <div className="max-h-[560px] space-y-2 overflow-y-auto pr-1">
              {entities.map((entity) => (
                <button
                  key={entity.id}
                  type="button"
                  className={
                    effectiveEntityId === entity.id
                      ? "w-full rounded-2xl border border-primary/40 bg-primary/10 px-4 py-3 text-left"
                      : "w-full rounded-2xl border border-border/70 bg-white/80 px-4 py-3 text-left transition-colors hover:bg-accent"
                  }
                  onClick={() => setSelectedEntityId(entity.id)}
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="font-medium text-foreground">{entity.name}</p>
                    {entity.entity_type ? <Badge variant="outline">{entity.entity_type}</Badge> : null}
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {messages.graph.entityStats(entity.mention_count, entity.relation_count)}
                  </p>
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="border-border/70 shadow-card">
        <CardHeader>
          <CardTitle>{detail?.name ?? messages.graph.detailTitle}</CardTitle>
          <CardDescription>
            {detail?.description ?? messages.graph.detailDescription}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6 lg:grid-cols-2">
          <section className="space-y-3">
            <h3 className="text-sm font-semibold text-foreground">{messages.graph.mentions}</h3>
            {(detail?.mentions ?? []).length === 0 ? (
              <p className="rounded-2xl bg-secondary/70 px-4 py-3 text-sm text-muted-foreground">
                {messages.graph.noMentions}
              </p>
            ) : (
              detail?.mentions.map((mention, index) => (
                <div key={`${mention.document_id}-${mention.chunk_id}-${index}`} className="rounded-2xl border border-border/70 bg-white/80 px-4 py-3 text-sm">
                  <p className="font-medium text-foreground">
                    {mention.document_name ?? messages.common.documentId(mention.document_id)}
                  </p>
                  <p className="mt-1 text-muted-foreground">
                    {mention.source_locator ?? mention.text_span ?? messages.graph.noSourceLocator}
                  </p>
                </div>
              ))
            )}
          </section>
          <section className="space-y-3">
            <h3 className="text-sm font-semibold text-foreground">{messages.graph.relations}</h3>
            {(detail?.relations ?? []).length === 0 ? (
              <p className="rounded-2xl bg-secondary/70 px-4 py-3 text-sm text-muted-foreground">
                {messages.graph.noRelations}
              </p>
            ) : (
              detail?.relations.map((relation) => (
                <div key={relation.id} className="rounded-2xl border border-border/70 bg-white/80 px-4 py-3 text-sm">
                  <p className="font-medium text-foreground">
                    {relation.source_entity_name} {"->"} {relation.relation_type} {"->"} {relation.target_entity_name}
                  </p>
                  <p className="mt-1 text-muted-foreground">
                    {relation.source_document_name ?? messages.graph.noSourceDocument}
                    {relation.source_locator ? ` · ${relation.source_locator}` : ""}
                  </p>
                </div>
              ))
            )}
          </section>
        </CardContent>
      </Card>
    </div>
  );
}
