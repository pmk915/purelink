"use client";

import { CitationCard } from "@/components/qa/citation-card";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useI18n } from "@/hooks/use-i18n";
import type { CitationLike, RetrievalResult } from "@/types";

export function EvidencePanel({
  evidences,
  compact = false
}: {
  evidences: Array<CitationLike | RetrievalResult>;
  compact?: boolean;
}) {
  const { messages } = useI18n();

  return (
    <Card className="border-border/70 shadow-card">
      <CardHeader>
        <CardTitle>{messages.qa.citationsTitle}</CardTitle>
        <CardDescription>{messages.qa.citationsDescription}</CardDescription>
      </CardHeader>
      <CardContent>
        {evidences.length === 0 ? (
          <div className="rounded-2xl bg-secondary/70 px-4 py-3 text-sm text-muted-foreground">
            {messages.qa.citationsEmpty}
          </div>
        ) : (
          <div className="grid max-h-[520px] gap-3 overflow-y-auto pr-1">
            {evidences.map((evidence, index) => (
              <CitationCard
                key={`${evidence.citation_marker ?? "evidence"}-${index}`}
                citation={evidence}
                compact={compact}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
