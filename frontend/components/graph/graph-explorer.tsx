"use client";

import {
  Download,
  FileText,
  LoaderCircle,
  Network,
  RefreshCcw,
  Search,
  X
} from "lucide-react";
import { useMemo, useState } from "react";
import type { FormEvent } from "react";

import { DocumentStatusDialog } from "@/components/documents/document-status-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/hooks/use-auth";
import { useDocumentStatus } from "@/hooks/use-document-status";
import { useI18n } from "@/hooks/use-i18n";
import { useKnowledgeGraphExport } from "@/hooks/use-knowledge-bases";
import type {
  KnowledgeBaseScope,
  KnowledgeGraphExport,
  KnowledgeGraphExportRelation
} from "@/types";

const ALL_RELATION_TYPES = "__all__";

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
  const [queryInput, setQueryInput] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [relationType, setRelationType] = useState("");
  const [selectedEntityId, setSelectedEntityId] = useState<number | null>(null);
  const [selectedRelation, setSelectedRelation] =
    useState<KnowledgeGraphExportRelation | null>(null);
  const [statusDocumentId, setStatusDocumentId] = useState<number | null>(null);

  const graphQuery = useKnowledgeGraphExport({
    token: accessToken,
    scope,
    knowledgeBaseId,
    teamId,
    params: {
      q: submittedQuery,
      relation_type: relationType || undefined,
      entity_id: selectedEntityId,
      limit_entities: 100,
      limit_relations: 300,
      limit_sources_per_relation: 5
    }
  });
  const graph = graphQuery.data;
  const selectedEntity = useMemo(
    () => graph?.entities.find((entity) => entity.id === selectedEntityId) ?? null,
    [graph?.entities, selectedEntityId]
  );
  const relationTypes = graph?.available_relation_types ?? [];
  const documentStatusQuery = useDocumentStatus({
    token: accessToken,
    scope,
    knowledgeBaseId,
    teamId,
    documentId: statusDocumentId,
    enabled: statusDocumentId !== null
  });

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmittedQuery(queryInput.trim());
    setSelectedEntityId(null);
  }

  function updateRelationType(value: string) {
    setRelationType(value === ALL_RELATION_TYPES ? "" : value);
    setSelectedEntityId(null);
  }

  function openDocumentStatus(documentId: number) {
    setSelectedRelation(null);
    setStatusDocumentId(documentId);
  }

  return (
    <div className="space-y-6">
      <Card className="border-border/70 shadow-card">
        <CardHeader>
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                <Network className="h-5 w-5" />
              </div>
              <div>
                <CardTitle>{messages.graph.title}</CardTitle>
                <CardDescription>{messages.graph.description}</CardDescription>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => graphQuery.refetch()}
                disabled={graphQuery.isFetching}
              >
                <RefreshCcw className="h-4 w-4" />
                {messages.graph.refresh}
              </Button>
              <GraphExportButtons graph={graph} />
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <form className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_220px_auto]" onSubmit={submitSearch}>
            <Input
              value={queryInput}
              onChange={(event) => setQueryInput(event.target.value)}
              placeholder={messages.graph.searchPlaceholder}
            />
            <select
              className="h-10 rounded-xl border border-input bg-background px-3 text-sm text-foreground shadow-sm outline-none transition-colors focus:border-ring focus:ring-2 focus:ring-ring/20"
              value={relationType || ALL_RELATION_TYPES}
              onChange={(event) => updateRelationType(event.target.value)}
              aria-label={messages.graph.relationType}
            >
              <option value={ALL_RELATION_TYPES}>{messages.graph.allRelationTypes}</option>
              {relationTypes.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
            <Button type="submit">
              <Search className="h-4 w-4" />
              {messages.graph.search}
            </Button>
          </form>

          <div className="grid gap-3 md:grid-cols-4">
            <SummaryTile
              label={messages.graph.summaryEntities}
              value={graph?.total_entities ?? 0}
              hint={messages.graph.filteredCount(graph?.filtered_entities ?? 0)}
            />
            <SummaryTile
              label={messages.graph.summaryRelations}
              value={graph?.total_relations ?? 0}
              hint={messages.graph.filteredCount(graph?.filtered_relations ?? 0)}
            />
            <SummaryTile
              label={messages.graph.relationTypes}
              value={relationTypes.length}
              hint={relationType || messages.graph.allRelationTypes}
            />
            <SummaryTile
              label={messages.graph.selectedEntity}
              value={selectedEntity?.name ?? messages.graph.allEntities}
              hint={selectedEntity ? messages.graph.oneHopNeighborhood : messages.graph.showingAll}
            />
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
        <Card className="border-border/70 shadow-card">
          <CardHeader>
            <CardTitle>{messages.graph.entities}</CardTitle>
            <CardDescription>{messages.graph.entityListDescription}</CardDescription>
          </CardHeader>
          <CardContent>
            <GraphEntityList
              graph={graph}
              loading={graphQuery.isLoading}
              error={graphQuery.error}
              selectedEntityId={selectedEntityId}
              onSelectEntity={setSelectedEntityId}
              onClearSelection={() => setSelectedEntityId(null)}
            />
          </CardContent>
        </Card>

        <Card className="border-border/70 shadow-card">
          <CardHeader>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <CardTitle>
                  {selectedEntity ? selectedEntity.name : messages.graph.relations}
                </CardTitle>
                <CardDescription>
                  {selectedEntity
                    ? messages.graph.oneHopNeighborhood
                    : messages.graph.relationListDescription}
                </CardDescription>
              </div>
              {selectedEntity?.entity_type ? (
                <Badge variant="outline">{selectedEntity.entity_type}</Badge>
              ) : null}
            </div>
          </CardHeader>
          <CardContent>
            <GraphRelationList
              graph={graph}
              loading={graphQuery.isLoading}
              error={graphQuery.error}
              onOpenSources={setSelectedRelation}
            />
          </CardContent>
        </Card>
      </div>

      <RelationSourcesDialog
        relation={selectedRelation}
        onClose={() => setSelectedRelation(null)}
        onViewDocumentStatus={openDocumentStatus}
      />
      <DocumentStatusDialog
        open={statusDocumentId !== null}
        status={documentStatusQuery.data}
        loading={documentStatusQuery.isLoading}
        error={documentStatusQuery.error}
        onClose={() => setStatusDocumentId(null)}
      />
    </div>
  );
}

function SummaryTile({
  label,
  value,
  hint
}: {
  label: string;
  value: string | number;
  hint: string;
}) {
  return (
    <div className="rounded-2xl border border-border/70 bg-secondary/40 px-4 py-3">
      <p className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
        {label}
      </p>
      <p className="mt-2 truncate text-lg font-semibold text-foreground">{value}</p>
      <p className="mt-1 truncate text-xs text-muted-foreground">{hint}</p>
    </div>
  );
}

function GraphEntityList({
  graph,
  loading,
  error,
  selectedEntityId,
  onSelectEntity,
  onClearSelection
}: {
  graph: KnowledgeGraphExport | undefined;
  loading: boolean;
  error: unknown;
  selectedEntityId: number | null;
  onSelectEntity: (entityId: number) => void;
  onClearSelection: () => void;
}) {
  const { messages } = useI18n();
  if (loading) {
    return <LoadingState />;
  }
  if (error) {
    return <ErrorState message={messages.graph.loadError} />;
  }
  const entities = graph?.entities ?? [];
  if (entities.length === 0) {
    return (
      <div className="rounded-2xl bg-secondary/70 px-4 py-3 text-sm text-muted-foreground">
        {messages.graph.empty}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {selectedEntityId !== null ? (
        <Button variant="ghost" size="sm" onClick={onClearSelection}>
          <X className="h-4 w-4" />
          {messages.graph.clearSelection}
        </Button>
      ) : null}
      <div className="max-h-[560px] space-y-2 overflow-y-auto pr-1">
        {entities.map((entity) => (
          <button
            key={entity.id}
            type="button"
            className={
              selectedEntityId === entity.id
                ? "w-full rounded-2xl border border-primary/40 bg-primary/10 px-4 py-3 text-left"
                : "w-full rounded-2xl border border-border/70 bg-white/80 px-4 py-3 text-left transition-colors hover:bg-accent"
            }
            onClick={() => onSelectEntity(entity.id)}
          >
            <div className="flex items-center justify-between gap-3">
              <p className="min-w-0 truncate font-medium text-foreground">{entity.name}</p>
              {entity.entity_type ? <Badge variant="outline">{entity.entity_type}</Badge> : null}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {messages.graph.entityStats(entity.mention_count, entity.relation_count)}
            </p>
          </button>
        ))}
      </div>
    </div>
  );
}

function GraphRelationList({
  graph,
  loading,
  error,
  onOpenSources
}: {
  graph: KnowledgeGraphExport | undefined;
  loading: boolean;
  error: unknown;
  onOpenSources: (relation: KnowledgeGraphExportRelation) => void;
}) {
  const { messages } = useI18n();
  if (loading) {
    return <LoadingState />;
  }
  if (error) {
    return <ErrorState message={messages.graph.loadError} />;
  }
  const relations = graph?.relations ?? [];
  if (relations.length === 0) {
    return (
      <div className="rounded-2xl bg-secondary/70 px-4 py-3 text-sm text-muted-foreground">
        {messages.graph.noRelations}
      </div>
    );
  }

  return (
    <div className="max-h-[620px] space-y-3 overflow-y-auto pr-1">
      {relations.map((relation) => (
        <div
          key={relation.id}
          className="rounded-2xl border border-border/70 bg-white/80 px-4 py-3 text-sm"
        >
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-medium text-foreground">
              {relation.source_entity} {"->"} {relation.target_entity}
            </p>
            <Badge variant="secondary">{relation.type}</Badge>
          </div>
          {relation.label ? (
            <p className="mt-1 break-words text-xs leading-5 text-muted-foreground">
              {relation.label}
            </p>
          ) : null}
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs text-muted-foreground">
              {messages.graph.sourceCount(relation.source_count)}
            </span>
            <Button variant="outline" size="sm" onClick={() => onOpenSources(relation)}>
              <FileText className="h-4 w-4" />
              {messages.graph.viewSources}
            </Button>
          </div>
        </div>
      ))}
    </div>
  );
}

function RelationSourcesDialog({
  relation,
  onClose,
  onViewDocumentStatus
}: {
  relation: KnowledgeGraphExportRelation | null;
  onClose: () => void;
  onViewDocumentStatus: (documentId: number) => void;
}) {
  const { messages } = useI18n();
  if (!relation) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 px-4 py-6"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="flex max-h-[82vh] w-full max-w-2xl flex-col overflow-hidden rounded-[28px] border border-border/70 bg-white shadow-soft"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="relation-sources-dialog-title"
      >
        <div className="flex items-start justify-between gap-4 border-b border-border/70 px-6 py-5">
          <div className="min-w-0 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <h2
                id="relation-sources-dialog-title"
                className="truncate text-lg font-semibold text-foreground"
              >
                {messages.graph.relationSources}
              </h2>
              <Badge variant="secondary">{relation.type}</Badge>
            </div>
            <p className="text-sm text-muted-foreground">
              {relation.source_entity} {"->"} {relation.target_entity}
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label={messages.common.cancel}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          {relation.sources.length === 0 ? (
            <div className="rounded-2xl bg-secondary/60 px-4 py-3 text-sm text-muted-foreground">
              {messages.graph.noSources}
            </div>
          ) : (
            <div className="space-y-3">
              {relation.sources.map((source, index) => (
                <div
                  key={`${source.document_id ?? "doc"}-${source.chunk_id ?? "chunk"}-${index}`}
                  className="rounded-2xl border border-border/70 bg-white/80 px-4 py-3"
                >
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-foreground">
                        {source.filename ?? messages.graph.noSourceDocument}
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {source.chunk_id
                          ? `${messages.graph.chunk} ${source.chunk_id}`
                          : messages.graph.noChunk}
                        {source.citation_unit_id
                          ? ` · ${messages.graph.citationUnit} ${source.citation_unit_id}`
                          : ""}
                      </p>
                    </div>
                    {source.document_id ? (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => onViewDocumentStatus(source.document_id as number)}
                      >
                        <FileText className="h-4 w-4" />
                        {messages.graph.viewDocumentStatus}
                      </Button>
                    ) : null}
                  </div>
                  {source.snippet ? (
                    <p className="mt-3 whitespace-pre-wrap break-words rounded-xl bg-secondary/50 px-3 py-2 text-xs leading-5 text-muted-foreground">
                      {source.snippet}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex justify-end border-t border-border/70 px-6 py-4">
          <Button variant="ghost" onClick={onClose}>
            {messages.common.cancel}
          </Button>
        </div>
      </div>
    </div>
  );
}

function GraphExportButtons({ graph }: { graph: KnowledgeGraphExport | undefined }) {
  const { messages } = useI18n();
  return (
    <>
      <Button
        variant="outline"
        size="sm"
        disabled={!graph}
        onClick={() => graph && downloadJson(graph)}
      >
        <Download className="h-4 w-4" />
        {messages.graph.exportJson}
      </Button>
      <Button
        variant="outline"
        size="sm"
        disabled={!graph}
        onClick={() => graph && downloadCsv("purelink-graph-entities.csv", entitiesCsv(graph))}
      >
        <Download className="h-4 w-4" />
        {messages.graph.exportEntitiesCsv}
      </Button>
      <Button
        variant="outline"
        size="sm"
        disabled={!graph}
        onClick={() => graph && downloadCsv("purelink-graph-relations.csv", relationsCsv(graph))}
      >
        <Download className="h-4 w-4" />
        {messages.graph.exportRelationsCsv}
      </Button>
    </>
  );
}

function LoadingState() {
  const { messages } = useI18n();
  return (
    <div className="flex items-center gap-2 rounded-2xl bg-secondary/60 px-4 py-6 text-sm text-muted-foreground">
      <LoaderCircle className="h-4 w-4 animate-spin" />
      {messages.common.loading}
    </div>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
      {message}
    </div>
  );
}

function downloadJson(graph: KnowledgeGraphExport) {
  downloadBlob(
    "purelink-graph-export.json",
    JSON.stringify(graph, null, 2),
    "application/json"
  );
}

function downloadCsv(filename: string, csv: string) {
  downloadBlob(filename, csv, "text/csv;charset=utf-8");
}

function downloadBlob(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = window.document.createElement("a");
  link.href = url;
  link.download = filename;
  window.document.body.appendChild(link);
  link.click();
  window.document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function entitiesCsv(graph: KnowledgeGraphExport) {
  return [
    ["id", "name", "entity_type", "mention_count", "relation_count"].map(csvCell).join(","),
    ...graph.entities.map((entity) =>
      [
        entity.id,
        entity.name,
        entity.entity_type,
        entity.mention_count,
        entity.relation_count
      ]
        .map(csvCell)
        .join(",")
    )
  ].join("\n");
}

function relationsCsv(graph: KnowledgeGraphExport) {
  return [
    [
      "id",
      "source_entity",
      "target_entity",
      "type",
      "label",
      "source_count"
    ].map(csvCell).join(","),
    ...graph.relations.map((relation) =>
      [
        relation.id,
        relation.source_entity,
        relation.target_entity,
        relation.type,
        relation.label,
        relation.source_count
      ]
        .map(csvCell)
        .join(",")
    )
  ].join("\n");
}

function csvCell(value: unknown) {
  return `"${String(value ?? "").replace(/"/g, "\"\"")}"`;
}
