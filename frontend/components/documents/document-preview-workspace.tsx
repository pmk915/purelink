"use client";

import { useEffect, useMemo, useRef, useState, type MutableRefObject } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import * as documentApi from "@/api/documents";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/hooks/use-auth";
import {
  usePersonalDocumentPreview,
  useTeamDocumentPreview
} from "@/hooks/use-documents";
import { useI18n } from "@/hooks/use-i18n";
import {
  formatLocatorLabel,
  formatMediaTime
} from "@/lib/preview-target";
import type {
  DocumentPreview,
  DocumentPreviewChunk,
  KnowledgeBaseScope,
  SourceLocatorKind
} from "@/types";

type PreviewParams = {
  chunkId: string | null;
  locatorKind: SourceLocatorKind | null;
  pageNumber: number | null;
  charStart: number | null;
  charEnd: number | null;
  startTime: number | null;
  endTime: number | null;
  sectionTitle: string | null;
  sourceType: string | null;
};

export function DocumentPreviewWorkspace({
  scope,
  teamId,
  knowledgeBaseId,
  documentId
}: {
  scope: KnowledgeBaseScope;
  teamId?: number;
  knowledgeBaseId: number;
  documentId: number;
}) {
  const { accessToken } = useAuth();
  const { messages } = useI18n();
  const searchParams = useSearchParams();
  const activeChunkRef = useRef<HTMLDivElement | null>(null);
  const [fileObjectUrl, setFileObjectUrl] = useState<string | null>(null);
  const [filePreviewFailed, setFilePreviewFailed] = useState(false);

  const personalPreviewQuery = usePersonalDocumentPreview(
    scope === "personal" ? accessToken : null,
    knowledgeBaseId,
    documentId
  );
  const teamPreviewQuery = useTeamDocumentPreview(
    scope === "team" ? accessToken : null,
    teamId ?? Number.NaN,
    knowledgeBaseId,
    documentId
  );
  const previewQuery = scope === "personal" ? personalPreviewQuery : teamPreviewQuery;
  const preview = previewQuery.data;
  const previewParams = useMemo(
    () => parsePreviewParams(searchParams),
    [searchParams]
  );
  const activeChunk = useMemo(
    () => resolveActiveChunk(preview, previewParams),
    [preview, previewParams]
  );
  const activeSourceType =
    previewParams.sourceType ||
    activeChunk?.source_type ||
    inferSourceTypeFromFilename(preview?.document.original_filename ?? "");
  const workspaceHref =
    scope === "team" && teamId
      ? `/teams/${teamId}/knowledge-bases/${knowledgeBaseId}`
      : `/knowledge-bases/${knowledgeBaseId}`;

  useEffect(() => {
    activeChunkRef.current?.scrollIntoView({
      block: "center",
      behavior: "smooth"
    });
  }, [activeChunk?.chunk_id]);

  useEffect(() => {
    if (!accessToken || !preview || !["pdf", "image"].includes(activeSourceType)) {
      setFileObjectUrl(null);
      return;
    }

    let isCurrent = true;
    let objectUrl: string | null = null;
    setFilePreviewFailed(false);

    const loadFile = async () => {
      try {
        const blob =
          scope === "personal"
            ? await documentApi.getPersonalDocumentFile(accessToken, knowledgeBaseId, documentId)
            : await documentApi.getTeamDocumentFile(
                accessToken,
                teamId as number,
                knowledgeBaseId,
                documentId
              );
        if (!isCurrent) {
          return;
        }
        objectUrl = URL.createObjectURL(blob);
        setFileObjectUrl(objectUrl);
      } catch {
        if (isCurrent) {
          setFilePreviewFailed(true);
          setFileObjectUrl(null);
        }
      }
    };

    void loadFile();

    return () => {
      isCurrent = false;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [accessToken, activeSourceType, documentId, knowledgeBaseId, preview, scope, teamId]);

  if (previewQuery.isLoading) {
    return (
      <div className="rounded-2xl border border-border/70 bg-white/80 px-6 py-10 text-sm text-muted-foreground">
        {messages.documents.previewLoading}
      </div>
    );
  }

  if (!preview || previewQuery.isError) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{messages.documents.previewTitle}</CardTitle>
          <CardDescription>{messages.documents.previewError}</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const locationLabel = formatLocatorLabel(
    activeChunk?.source_locator ?? null,
    activeChunk?.preview_target ?? null
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm text-muted-foreground">{messages.documents.previewTitle}</p>
          <h1 className="text-2xl font-semibold tracking-normal text-foreground">
            {preview.document.original_filename}
          </h1>
        </div>
        <Link
          className={buttonVariants({ variant: "outline", size: "sm" })}
          href={workspaceHref}
        >
          <ArrowLeft className="h-4 w-4" />
          {messages.documents.previewBack}
        </Link>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <PreviewMainPanel
          activeChunk={activeChunk}
          activeChunkRef={activeChunkRef}
          activeSourceType={activeSourceType}
          fileObjectUrl={fileObjectUrl}
          filePreviewFailed={filePreviewFailed}
          preview={preview}
          previewParams={previewParams}
        />

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">{messages.documents.previewLocation}</CardTitle>
            <CardDescription>
              {locationLabel ?? activeSourceType.toUpperCase()}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {activeChunk ? (
              <>
                <div>
                  <p className="text-xs font-medium uppercase text-muted-foreground">
                    {messages.documents.previewSnippet}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-foreground">
                    {activeChunk.snippet}
                  </p>
                </div>
                <LocatorDetails chunk={activeChunk} />
              </>
            ) : (
              <p className="text-sm text-muted-foreground">
                {messages.documents.previewNoChunks}
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function PreviewMainPanel({
  activeChunk,
  activeChunkRef,
  activeSourceType,
  fileObjectUrl,
  filePreviewFailed,
  preview,
  previewParams
}: {
  activeChunk: DocumentPreviewChunk | null;
  activeChunkRef: MutableRefObject<HTMLDivElement | null>;
  activeSourceType: string;
  fileObjectUrl: string | null;
  filePreviewFailed: boolean;
  preview: DocumentPreview;
  previewParams: PreviewParams;
}) {
  const { messages } = useI18n();

  if (activeSourceType === "pdf") {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{messages.documents.previewPdfPage(previewParams.pageNumber ?? activeChunk?.page_number ?? 1)}</CardTitle>
          <CardDescription>{activeChunk?.snippet}</CardDescription>
        </CardHeader>
        <CardContent>
          {fileObjectUrl ? (
            <iframe
              className="h-[72vh] w-full rounded-xl border border-border bg-white"
              src={`${fileObjectUrl}#page=${previewParams.pageNumber ?? activeChunk?.page_number ?? 1}`}
              title={preview.document.original_filename}
            />
          ) : (
            <PreviewUnavailable failed={filePreviewFailed} />
          )}
        </CardContent>
      </Card>
    );
  }

  if (activeSourceType === "image") {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{messages.documents.previewImageRegion}</CardTitle>
          <CardDescription>{activeChunk?.snippet}</CardDescription>
        </CardHeader>
        <CardContent>
          {fileObjectUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              alt={messages.documents.previewOriginalImageAlt(preview.document.original_filename)}
              className="max-h-[72vh] w-full rounded-xl border border-border object-contain"
              src={fileObjectUrl}
            />
          ) : (
            <PreviewUnavailable failed={filePreviewFailed} />
          )}
        </CardContent>
      </Card>
    );
  }

  if (activeSourceType === "audio" || activeSourceType === "video") {
    const range =
      typeof activeChunk?.start_time === "number" && typeof activeChunk.end_time === "number"
        ? `${formatMediaTime(activeChunk.start_time)} - ${formatMediaTime(activeChunk.end_time)}`
        : null;
    return (
      <Card>
        <CardHeader>
          <CardTitle>
            {range ? messages.documents.previewMediaRange(range) : preview.document.original_filename}
          </CardTitle>
          <CardDescription>{activeChunk?.snippet}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="rounded-xl border border-border bg-secondary/40 p-5">
            <p className="text-sm leading-6 text-foreground">
              {activeChunk?.text ?? messages.documents.previewNoChunks}
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{messages.documents.previewExtractedText}</CardTitle>
        <CardDescription>{preview.document.original_filename}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {preview.chunks.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {messages.documents.previewNoChunks}
          </p>
        ) : null}
        {preview.chunks.map((chunk) => {
          const isActive = chunk.chunk_id === activeChunk?.chunk_id;
          return (
            <div
              className={
                isActive
                  ? "rounded-xl border border-primary/40 bg-primary/10 p-4"
                  : "rounded-xl border border-border bg-white/70 p-4"
              }
              key={chunk.chunk_id}
              ref={isActive ? (node) => {
                activeChunkRef.current = node;
              } : undefined}
            >
              {chunk.section_title ? (
                <p className="mb-2 text-xs font-medium uppercase text-muted-foreground">
                  {chunk.section_title}
                </p>
              ) : null}
              <TextPreviewContent
                chunk={chunk}
                isActive={isActive}
                previewParams={previewParams}
              />
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

function TextPreviewContent({
  chunk,
  isActive,
  previewParams
}: {
  chunk: DocumentPreviewChunk;
  isActive: boolean;
  previewParams: PreviewParams;
}) {
  const highlight = isActive ? getTextHighlight(chunk, previewParams) : null;
  if (!highlight) {
    return (
      <p className="whitespace-pre-wrap text-sm leading-7 text-foreground">
        {chunk.text}
      </p>
    );
  }

  return (
    <p className="whitespace-pre-wrap text-sm leading-7 text-foreground">
      {highlight.before}
      <mark className="rounded bg-amber-200/80 px-1 py-0.5 text-amber-950">
        {highlight.match}
      </mark>
      {highlight.after}
    </p>
  );
}


function LocatorDetails({ chunk }: { chunk: DocumentPreviewChunk }) {
  const { messages } = useI18n();
  const locator = chunk.source_locator;
  const parts: string[] = [];
  if (typeof chunk.page_number === "number") {
    parts.push(messages.qa.citationPage(chunk.page_number));
  }
  if (typeof chunk.start_time === "number" && typeof chunk.end_time === "number") {
    parts.push(messages.qa.citationTimeRange(
      formatMediaTime(chunk.start_time),
      formatMediaTime(chunk.end_time)
    ));
  }
  if (chunk.section_title) {
    parts.push(messages.qa.citationSection(chunk.section_title));
  }
  if (locator?.region_hint) {
    parts.push(messages.documents.previewImageRegion);
  }
  if (typeof chunk.char_start === "number" && typeof chunk.char_end === "number") {
    parts.push(messages.qa.citationCharRange(chunk.char_start, chunk.char_end));
  }

  return (
    <div className="rounded-xl bg-secondary/50 p-3 text-xs leading-6 text-muted-foreground">
      {parts.length > 0 ? parts.join(" · ") : locator?.source_locator_text}
    </div>
  );
}

function PreviewUnavailable({ failed }: { failed: boolean }) {
  const { messages } = useI18n();
  return (
    <div className="rounded-xl border border-dashed border-border bg-secondary/40 p-6 text-sm text-muted-foreground">
      {failed ? messages.documents.previewFileUnavailable : messages.documents.previewLoading}
    </div>
  );
}

function parsePreviewParams(searchParams: URLSearchParams): PreviewParams {
  return {
    chunkId: searchParams.get("chunk_id"),
    locatorKind: searchParams.get("locator_kind") as SourceLocatorKind | null,
    pageNumber: getNumberParam(searchParams, "page"),
    charStart: getNumberParam(searchParams, "char_start"),
    charEnd: getNumberParam(searchParams, "char_end"),
    startTime: getNumberParam(searchParams, "start_time"),
    endTime: getNumberParam(searchParams, "end_time"),
    sectionTitle: searchParams.get("section"),
    sourceType: searchParams.get("source_type")
  };
}

function resolveActiveChunk(
  preview: DocumentPreview | undefined,
  params: PreviewParams
) {
  if (!preview || preview.chunks.length === 0) {
    return null;
  }

  if (params.chunkId) {
    const exactChunk = preview.chunks.find((chunk) => chunk.chunk_id === params.chunkId);
    if (exactChunk) {
      return exactChunk;
    }
  }

  if (typeof params.pageNumber === "number") {
    const pageChunk = preview.chunks.find((chunk) => chunk.page_number === params.pageNumber);
    if (pageChunk) {
      return pageChunk;
    }
  }

  if (typeof params.startTime === "number" && typeof params.endTime === "number") {
    const timedChunk = preview.chunks.find(
      (chunk) =>
        typeof chunk.start_time === "number" &&
        typeof chunk.end_time === "number" &&
        chunk.start_time <= params.startTime! &&
        chunk.end_time >= params.endTime!
    );
    if (timedChunk) {
      return timedChunk;
    }
  }

  if (typeof params.charStart === "number" && typeof params.charEnd === "number") {
    const textChunk = preview.chunks.find(
      (chunk) =>
        typeof chunk.char_start === "number" &&
        typeof chunk.char_end === "number" &&
        chunk.char_start <= params.charStart! &&
        chunk.char_end >= params.charEnd!
    );
    if (textChunk) {
      return textChunk;
    }
  }

  if (params.sectionTitle) {
    const sectionChunk = preview.chunks.find(
      (chunk) => chunk.section_title === params.sectionTitle
    );
    if (sectionChunk) {
      return sectionChunk;
    }
  }

  return preview.chunks[0];
}

function getTextHighlight(
  chunk: DocumentPreviewChunk,
  params: PreviewParams
) {
  const chunkStart = chunk.char_start;
  const targetStart = params.charStart ?? chunk.char_start;
  const targetEnd = params.charEnd ?? chunk.char_end;

  if (
    typeof chunkStart !== "number" ||
    typeof targetStart !== "number" ||
    typeof targetEnd !== "number" ||
    targetEnd <= targetStart
  ) {
    return null;
  }

  const localStart = Math.max(0, targetStart - chunkStart);
  const localEnd = Math.min(chunk.text.length, targetEnd - chunkStart);
  if (localEnd <= localStart) {
    return null;
  }

  return {
    before: chunk.text.slice(0, localStart),
    match: chunk.text.slice(localStart, localEnd),
    after: chunk.text.slice(localEnd)
  };
}

function getNumberParam(searchParams: URLSearchParams, key: string) {
  const value = searchParams.get(key);
  if (!value) {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function inferSourceTypeFromFilename(filename: string) {
  const normalized = filename.toLowerCase();
  if (normalized.endsWith(".pdf")) {
    return "pdf";
  }
  if (normalized.endsWith(".png") || normalized.endsWith(".jpg") || normalized.endsWith(".jpeg")) {
    return "image";
  }
  if (normalized.endsWith(".mp3") || normalized.endsWith(".wav") || normalized.endsWith(".m4a")) {
    return "audio";
  }
  if (normalized.endsWith(".mp4") || normalized.endsWith(".mov") || normalized.endsWith(".m4v")) {
    return "video";
  }
  return "text";
}
