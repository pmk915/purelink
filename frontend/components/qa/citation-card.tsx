"use client";

import { useI18n } from "@/hooks/use-i18n";
import type { CitationLike, RetrievalResult } from "@/types";


function hasScore(citation: CitationLike | RetrievalResult): citation is RetrievalResult {
  return typeof (citation as RetrievalResult).score === "number";
}


function formatMediaTime(seconds: number) {
  const normalized = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(normalized / 3600);
  const minutes = Math.floor((normalized % 3600) / 60);
  const remainingSeconds = normalized % 60;
  const minuteSecond = `${String(minutes).padStart(2, "0")}:${String(remainingSeconds).padStart(2, "0")}`;
  if (hours <= 0) {
    return minuteSecond;
  }
  return `${hours}:${minuteSecond}`;
}


function formatSourceLabel(sourceType: string | null) {
  switch (sourceType) {
    case "pdf":
      return "PDF";
    case "image":
      return "Image";
    case "audio":
      return "Audio";
    case "video":
      return "Video";
    case "md":
      return "Markdown";
    case "docx":
      return "DOCX";
    case "txt":
      return "Text";
    default:
      return sourceType ? sourceType.toUpperCase() : "Text";
  }
}


export function CitationCard({
  citation
}: {
  citation: CitationLike | RetrievalResult;
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
  const mediaStartTime =
    typeof locator?.start_time === "number"
      ? locator.start_time
      : typeof citation.start_time === "number"
        ? citation.start_time
        : null;
  const mediaEndTime =
    typeof locator?.end_time === "number"
      ? locator.end_time
      : typeof citation.end_time === "number"
        ? citation.end_time
        : null;
  const hasMediaRange = mediaStartTime !== null && mediaEndTime !== null;
  const sectionTitle = locator?.section_title || citation.section_title;
  const headingPath = locator?.heading_path || citation.heading_path;
  const locationFallback = locator?.source_locator_text;
  const textRangeStart = locator?.char_start;
  const textRangeEnd = locator?.char_end;
  const hasTextRange =
    locator?.kind === "text_range" &&
    typeof textRangeStart === "number" &&
    typeof textRangeEnd === "number";

  return (
    <div className="rounded-2xl border border-border/70 bg-white/80 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-foreground">{documentName}</p>
          <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
            <span>{sourceLabel}</span>
            {hasPageNumber ? (
              <span>{messages.qa.citationPage(pageNumber)}</span>
            ) : null}
            {locator?.kind === "image_region" ? (
              <span>{messages.qa.citationImageRegion}</span>
            ) : null}
            {hasMediaRange ? (
              <span>
                {messages.qa.citationTimeRange(
                  formatMediaTime(mediaStartTime),
                  formatMediaTime(mediaEndTime)
                )}
              </span>
            ) : null}
            {headingPath && headingPath.length > 1 ? (
              <span>{messages.qa.citationHeadingPath(headingPath.join(" / "))}</span>
            ) : null}
            {sectionTitle ? (
              <span>{messages.qa.citationSection(sectionTitle)}</span>
            ) : null}
            {!hasPageNumber &&
            !hasMediaRange &&
            !sectionTitle &&
            hasTextRange ? (
              <span>{messages.qa.citationCharRange(textRangeStart, textRangeEnd)}</span>
            ) : null}
            {!hasPageNumber &&
            !hasMediaRange &&
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
      <p className="mt-3 text-sm leading-6 text-foreground">{snippet}</p>
    </div>
  );
}
