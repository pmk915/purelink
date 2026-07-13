"use client";

import Link from "next/link";
import { ExternalLink } from "lucide-react";

import { getCitationDisplayDetails } from "@/components/qa/citation-details";
import { buttonVariants } from "@/components/ui/button";
import { useI18n } from "@/hooks/use-i18n";
import {
  buildPreviewUrl
} from "@/lib/preview-target";
import type { CitationLike, RetrievalResult } from "@/types";


type ScoredCitation = CitationLike & {
  score: number;
  vector_score?: number | null;
  keyword_score?: number | null;
  graph_score?: number | null;
};


function hasScore(citation: CitationLike | RetrievalResult): citation is ScoredCitation {
  return typeof citation.score === "number";
}

function scoreParts(citation: ScoredCitation) {
  return [
    typeof citation.vector_score === "number" ? `vector ${citation.vector_score.toFixed(3)}` : null,
    typeof citation.keyword_score === "number" ? `keyword ${citation.keyword_score.toFixed(3)}` : null,
    typeof citation.graph_score === "number" ? `graph ${citation.graph_score.toFixed(3)}` : null
  ].filter(Boolean);
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
  const documentName = citation.document_name || messages.graph.noSourceDocument;
  const details = getCitationDisplayDetails(citation);
  const previewUrl = buildPreviewUrl(citation);
  const hasPageNumber = details.pageNumber !== null;
  const hasTextRange = details.charStart !== null && details.charEnd !== null;

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
            <span>{details.sourceLabel}</span>
            {typeof details.pageNumber === "number" ? (
              <span>{messages.qa.citationPage(details.pageNumber)}</span>
            ) : null}
            {details.headingPath.length > 1 ? (
              <span>{messages.qa.citationHeadingPath(details.headingPath.join(" / "))}</span>
            ) : null}
            {details.sectionTitle ? (
              <span>{messages.qa.citationSection(details.sectionTitle)}</span>
            ) : null}
            {!hasPageNumber &&
            !details.sectionTitle &&
            typeof details.charStart === "number" &&
            typeof details.charEnd === "number" ? (
              <span>{messages.qa.citationCharRange(details.charStart, details.charEnd)}</span>
            ) : null}
            {!hasPageNumber &&
            !details.sectionTitle &&
            !hasTextRange &&
            details.sourceLocatorText ? (
              <span>{details.sourceLocatorText}</span>
            ) : null}
          </div>
        </div>
        {hasScore(citation) ? (
          <div className="text-right text-xs text-muted-foreground">
            <div>{messages.qa.citationScore(citation.score)}</div>
            {scoreParts(citation).length > 0 ? (
              <div className="mt-1 max-w-[220px] break-words">
                {scoreParts(citation).join(" · ")}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
      <p
        className={
          compact
            ? "mt-2 line-clamp-4 whitespace-pre-wrap break-words text-sm leading-6 text-foreground [overflow-wrap:anywhere]"
            : "mt-3 whitespace-pre-wrap break-words text-sm leading-6 text-foreground [overflow-wrap:anywhere]"
        }
      >
        <span className="mb-1 block text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
          {messages.qa.evidenceSnippet}
        </span>
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
