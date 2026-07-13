"use client";

import { ExternalLink, FileText, MapPin, Quote, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";

import { getCitationDisplayDetails } from "@/components/qa/citation-details";
import { Button, buttonVariants } from "@/components/ui/button";
import { useI18n } from "@/hooks/use-i18n";
import { buildPreviewUrl } from "@/lib/preview-target";
import type { Citation } from "@/types";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "summary",
  "[tabindex]:not([tabindex='-1'])"
].join(",");

export function CitationDrawer({
  citation,
  displayNumber,
  citationOptions,
  onSelect,
  onClose
}: {
  citation: Citation;
  displayNumber: string;
  citationOptions: Array<{ citation: Citation; displayNumber: string }>;
  onSelect: (selection: { citation: Citation; displayNumber: string }) => void;
  onClose: () => void;
}) {
  const { messages } = useI18n();
  const titleId = useId();
  const panelRef = useRef<HTMLElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const details = getCitationDisplayDetails(citation);
  const previewUrl = buildPreviewUrl(citation);
  const evidenceText = citation.text || citation.snippet || "";
  const documentName = citation.document_name || messages.qa.citationUnknownDocument;

  useEffect(() => {
    const previouslyFocused = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButtonRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") {
        return;
      }

      const focusableElements = Array.from(
        panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR) ?? []
      ).filter((element) => !element.hasAttribute("disabled"));
      if (focusableElements.length === 0) {
        event.preventDefault();
        return;
      }

      const firstElement = focusableElements[0];
      const lastElement = focusableElements[focusableElements.length - 1];
      if (event.shiftKey && document.activeElement === firstElement) {
        event.preventDefault();
        lastElement.focus();
      } else if (!event.shiftKey && document.activeElement === lastElement) {
        event.preventDefault();
        firstElement.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      if (previouslyFocused instanceof HTMLElement && previouslyFocused.isConnected) {
        previouslyFocused.focus();
      }
    };
  }, [onClose]);

  return createPortal(
    <div
      className="fixed inset-0 z-[70] bg-slate-950/35 motion-safe:animate-[citation-backdrop-in_160ms_ease-out]"
      data-testid="citation-drawer-backdrop"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
      role="presentation"
    >
      <aside
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        data-testid="citation-drawer"
        className="absolute inset-y-0 right-0 flex w-full max-w-full flex-col overflow-hidden border-l border-border/70 bg-white shadow-2xl motion-safe:animate-[citation-drawer-in_180ms_ease-out] sm:w-[460px]"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="flex shrink-0 items-start justify-between gap-4 border-b border-border/70 px-5 py-4 sm:px-6">
          <div className="min-w-0">
            <p className="text-xs font-medium uppercase tracking-[0.16em] text-primary">
              {messages.qa.citationTitle(displayNumber)}
            </p>
            <h2 id={titleId} className="mt-1 truncate text-base font-semibold text-foreground">
              {documentName}
            </h2>
          </div>
          <Button
            ref={closeButtonRef}
            type="button"
            variant="ghost"
            size="sm"
            className="h-9 w-9 shrink-0 px-0"
            aria-label={messages.qa.closeCitation}
            data-testid="citation-drawer-close"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </Button>
        </header>

        {citationOptions.length > 1 ? (
          <nav
            aria-label={messages.qa.citationNavigation}
            className="flex shrink-0 gap-2 overflow-x-auto border-b border-border/60 px-5 py-2.5 sm:px-6"
          >
            {citationOptions.map((option) => {
              const marker = option.citation.citation_marker;
              const isActive = option.citation === citation;
              return (
                <button
                  key={marker ?? option.displayNumber}
                  type="button"
                  data-testid={`citation-drawer-marker-${marker ?? option.displayNumber}`}
                  aria-current={isActive ? "true" : undefined}
                  aria-label={messages.qa.viewCitationAria(
                    option.displayNumber,
                    option.citation.document_name || messages.qa.citationUnknownDocument
                  )}
                  className={
                    isActive
                      ? "inline-flex h-7 min-w-7 items-center justify-center rounded-md border border-primary/30 bg-primary/10 px-2 text-xs font-semibold text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      : "inline-flex h-7 min-w-7 items-center justify-center rounded-md border border-border bg-secondary/60 px-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  }
                  onClick={() => onSelect(option)}
                >
                  [{option.displayNumber}]
                </button>
              );
            })}
          </nav>
        ) : null}

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-5 sm:px-6">
          <div className="space-y-6">
            {!citation.citation_ready ? (
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-sm text-amber-800">
                {messages.qa.limitedSourceDetails}
              </div>
            ) : null}

            <section aria-labelledby={`${titleId}-source`}>
              <div className="flex items-center gap-2">
                <MapPin className="h-4 w-4 text-muted-foreground" />
                <h3 id={`${titleId}-source`} className="text-sm font-semibold text-foreground">
                  {messages.qa.sourceDetails}
                </h3>
              </div>
              <dl className="mt-3 divide-y divide-border/60 rounded-lg border border-border/70 bg-secondary/25 px-3">
                <DetailRow label={messages.qa.sourceType} value={details.sourceLabel} />
                {details.pageNumber !== null ? (
                  <DetailRow label={messages.qa.page} value={String(details.pageNumber)} />
                ) : null}
                {details.sectionTitle ? (
                  <DetailRow label={messages.qa.section} value={details.sectionTitle} />
                ) : null}
                {details.headingPath.length > 0 ? (
                  <DetailRow
                    label={messages.qa.headingPath}
                    value={details.headingPath.join(" / ")}
                  />
                ) : null}
                {details.charStart !== null && details.charEnd !== null ? (
                  <DetailRow
                    label={messages.qa.characterRange}
                    value={`${details.charStart}-${details.charEnd}`}
                  />
                ) : null}
                {details.sourceLocatorText ? (
                  <DetailRow
                    label={messages.qa.sourceLocation}
                    value={details.sourceLocatorText}
                  />
                ) : null}
              </dl>
            </section>

            <section aria-labelledby={`${titleId}-evidence`}>
              <div className="flex items-center gap-2">
                <Quote className="h-4 w-4 text-muted-foreground" />
                <h3 id={`${titleId}-evidence`} className="text-sm font-semibold text-foreground">
                  {messages.qa.quotedEvidence}
                </h3>
              </div>
              <blockquote className="mt-3 whitespace-pre-wrap break-words rounded-lg border-l-2 border-primary/50 bg-secondary/45 px-4 py-3 text-sm leading-7 text-foreground [overflow-wrap:anywhere]">
                {evidenceText}
              </blockquote>
            </section>

            {previewUrl ? (
              <Link
                href={previewUrl}
                data-testid="citation-drawer-view-source"
                className={buttonVariants({
                  variant: "outline",
                  className: "w-full justify-center sm:w-auto"
                })}
              >
                <ExternalLink className="h-4 w-4" />
                {messages.qa.citationViewSource}
              </Link>
            ) : null}

            <details className="rounded-lg border border-border/70 bg-white px-4 py-3">
              <summary className="cursor-pointer text-sm font-medium text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                {messages.qa.technicalDetails}
              </summary>
              <dl className="mt-3 divide-y divide-border/60 text-xs">
                <DetailRow
                  label={messages.qa.citationReady}
                  value={citation.citation_ready ? messages.common.yes : messages.common.no}
                />
                {citation.retrieval_mode ? (
                  <DetailRow
                    label={messages.qa.retrievalMode}
                    value={messages.qa.retrievalModeLabel(citation.retrieval_mode)}
                  />
                ) : null}
                {typeof citation.score === "number" ? (
                  <DetailRow
                    label={messages.qa.evidenceScore}
                    value={citation.score.toFixed(3)}
                  />
                ) : null}
                <DetailRow label={messages.qa.sourceType} value={details.sourceLabel} />
                {details.pageNumber !== null ? (
                  <DetailRow label={messages.qa.page} value={String(details.pageNumber)} />
                ) : null}
                {details.charStart !== null && details.charEnd !== null ? (
                  <DetailRow
                    label={messages.qa.characterRange}
                    value={`${details.charStart}-${details.charEnd}`}
                  />
                ) : null}
                {details.sourceLocatorText ? (
                  <DetailRow
                    label={messages.qa.sourceLocation}
                    value={details.sourceLocatorText}
                  />
                ) : null}
              </dl>
            </details>

            <div className="flex items-start gap-2 text-xs leading-5 text-muted-foreground">
              <FileText className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>{messages.qa.finalEvidenceNote}</span>
            </div>
          </div>
        </div>
      </aside>
    </div>,
    document.body
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[minmax(100px,0.38fr)_minmax(0,1fr)] gap-3 py-2.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="break-words text-right text-xs text-foreground [overflow-wrap:anywhere]">
        {value}
      </dd>
    </div>
  );
}
