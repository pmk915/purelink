"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { CitationDrawer } from "@/components/qa/citation-drawer";
import { useI18n } from "@/hooks/use-i18n";
import { parseCitationMarkers } from "@/lib/citation-markers";
import { cn } from "@/lib/utils";
import type { Citation } from "@/types";

type SelectedCitation = {
  citation: Citation;
  displayNumber: string;
} | null;

export function CitationAwareAnswer({
  answer,
  citations,
  className
}: {
  answer: string;
  citations: Citation[];
  className?: string;
}) {
  const { messages } = useI18n();
  const [selectedCitation, setSelectedCitation] = useState<SelectedCitation>(null);
  const segments = useMemo(
    () => parseCitationMarkers(answer, citations),
    [answer, citations]
  );
  const citationOptions = useMemo(() => {
    const options = new Map<string, Exclude<SelectedCitation, null>>();
    for (const segment of segments) {
      if (segment.type === "citation" && !options.has(segment.marker)) {
        options.set(segment.marker, {
          citation: segment.citation,
          displayNumber: segment.displayNumber
        });
      }
    }
    return Array.from(options.values());
  }, [segments]);
  const closeDrawer = useCallback(() => setSelectedCitation(null), []);

  useEffect(() => {
    setSelectedCitation(null);
  }, [answer, citations]);

  return (
    <>
      <p className={cn("whitespace-pre-wrap", className)}>
        {segments.map((segment, index) =>
          segment.type === "text" ? (
            <span key={`text-${index}`}>{segment.text}</span>
          ) : (
            <button
              key={`${segment.marker}-${index}`}
              type="button"
              data-testid={`citation-marker-${segment.marker}`}
              aria-label={messages.qa.viewCitationAria(
                segment.displayNumber,
                segment.citation.document_name || messages.qa.citationUnknownDocument
              )}
              aria-haspopup="dialog"
              aria-expanded={selectedCitation?.citation === segment.citation}
              className="mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-md border border-border/80 bg-secondary px-1 text-[11px] font-semibold leading-none text-primary align-baseline transition-colors hover:border-primary/40 hover:bg-primary/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
              onClick={() =>
                setSelectedCitation({
                  citation: segment.citation,
                  displayNumber: segment.displayNumber
                })
              }
            >
              [{segment.displayNumber}]
            </button>
          )
        )}
      </p>

      {selectedCitation ? (
        <CitationDrawer
          citation={selectedCitation.citation}
          displayNumber={selectedCitation.displayNumber}
          citationOptions={citationOptions}
          onSelect={setSelectedCitation}
          onClose={closeDrawer}
        />
      ) : null}
    </>
  );
}
