"use client";

import Link from "next/link";
import { ExternalLink } from "lucide-react";

import { buttonVariants } from "@/components/ui/button";
import { useI18n } from "@/hooks/use-i18n";
import {
  buildPreviewUrl
} from "@/lib/preview-target";
import type { CitationLike, RetrievalResult } from "@/types";


function hasScore(citation: CitationLike | RetrievalResult): citation is RetrievalResult {
  return typeof (citation as RetrievalResult).score === "number";
}


function formatSourceLabel(sourceType: string | null) {
  switch (sourceType) {
    case "pdf":
      return "PDF";
    case "markdown":
    case "md":
      return "Markdown";
    case "docx":
      return "DOCX";
    case "text":
    case "txt":
      return "Text";
    default:
      return sourceType ? sourceType.toUpperCase() : "Text";
  }
}


export function CitationCard({
  citation,
  compact = false
}: {
  citation: CitationLike | RetrievalResult;
  compact?: boolean;
}) {
  const { messages } = useI18n();
  const snippet = citation.snippet || citation.text;
  const documentName = citation.document_name || messages.common.documentId(citation.document_id);
  const locator = citation.source_locator;
  const sourceLabel = formatSourceLabel(citation.source_type);
  const pageNumber =
    typeof locator?.page_number === "number"
      ? locator.page_number
      : typeof citation.page_number === "number"
        ? citation.page_number
        : null;
  const hasPageNumber = pageNumber !== null;
  const sectionTitle = locator?.section_title || citation.section_title;
  const headingPath = locator?.heading_path || citation.heading_path;
  const locationFallback = locator?.source_locator_text;
  const previewUrl = buildPreviewUrl(citation);
  const textRangeStart = locator?.char_start;
  const textRangeEnd = locator?.char_end;
  const hasTextRange =
    locator?.kind === "text_range" &&
    typeof textRangeStart === "number" &&
    typeof textRangeEnd === "number";

  return (
    <div
      data-testid="citation-card"
      className={
        compact
          ? "rounded-2xl border border-border/50 bg-white/70 px-3.5 py-3"
          : "rounded-2xl border border-border/70 bg-white/80 p-4"
      }
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            {citation.citation_marker ? (
              <span className="rounded-full bg-secondary px-2 py-0.5 text-[11px] font-medium text-foreground">
                [{citation.citation_marker}]
              </span>
            ) : null}
            <p className={compact ? "text-xs font-medium text-foreground" : "text-sm font-medium text-foreground"}>
              {documentName}
            </p>
          </div>
          <div className={compact ? "mt-1.5 flex flex-wrap gap-2 text-[11px] text-muted-foreground" : "mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground"}>
            <span>{sourceLabel}</span>
            {hasPageNumber ? (
              <span>{messages.qa.citationPage(pageNumber)}</span>
            ) : null}
            {headingPath && headingPath.length > 1 ? (
              <span>{messages.qa.citationHeadingPath(headingPath.join(" / "))}</span>
            ) : null}
            {sectionTitle ? (
              <span>{messages.qa.citationSection(sectionTitle)}</span>
            ) : null}
            {!hasPageNumber &&
            !sectionTitle &&
            hasTextRange ? (
              <span>{messages.qa.citationCharRange(textRangeStart, textRangeEnd)}</span>
            ) : null}
            {!hasPageNumber &&
            !sectionTitle &&
            !hasTextRange &&
            locationFallback ? (
              <span>{locationFallback}</span>
            ) : null}
          </div>
        </div>
        {hasScore(citation) ? (
          <span className="text-xs text-muted-foreground">
            {messages.qa.citationScore(citation.score)}
          </span>
        ) : null}
      </div>
      <p
        className={
          compact
            ? "mt-2 line-clamp-4 whitespace-pre-wrap break-words text-sm leading-6 text-foreground [overflow-wrap:anywhere]"
            : "mt-3 whitespace-pre-wrap break-words text-sm leading-6 text-foreground [overflow-wrap:anywhere]"
        }
      >
        {snippet}
      </p>
      {previewUrl ? (
        <div className={compact ? "mt-3" : "mt-4"}>
          <Link
            className={buttonVariants({
              variant: "outline",
              size: "sm",
              className: compact ? "h-8 rounded-xl px-2.5 text-xs" : "rounded-xl"
            })}
            href={previewUrl}
          >
            <ExternalLink className="h-4 w-4" />
            {messages.qa.citationViewSource}
          </Link>
        </div>
      ) : null}
    </div>
  );
}
