"use client";

import { Database, Users } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { useI18n } from "@/hooks/use-i18n";
import { cn } from "@/lib/utils";

export type AccessibleKnowledgeBaseOption = {
  id: number;
  name: string;
  description: string | null;
  scope: "personal" | "team";
  teamId?: number | null;
  teamName?: string | null;
};

export function KnowledgeBaseSelector({
  personalKnowledgeBases,
  teamKnowledgeBases,
  selectedKey,
  onSelect,
  emptyLabel,
  personalLabel,
  teamLabel
}: {
  personalKnowledgeBases: AccessibleKnowledgeBaseOption[];
  teamKnowledgeBases: AccessibleKnowledgeBaseOption[];
  selectedKey: string | null;
  onSelect: (item: AccessibleKnowledgeBaseOption) => void;
  emptyLabel: string;
  personalLabel: string;
  teamLabel: string;
}) {
  const { messages } = useI18n();
  const hasAnyKnowledgeBase =
    personalKnowledgeBases.length > 0 || teamKnowledgeBases.length > 0;

  if (!hasAnyKnowledgeBase) {
    return (
      <div className="rounded-2xl bg-secondary/60 px-4 py-3 text-sm text-muted-foreground">
        {emptyLabel}
      </div>
    );
  }

  const sections = [
    {
      key: "personal",
      label: personalLabel,
      items: personalKnowledgeBases
    },
    {
      key: "team",
      label: teamLabel,
      items: teamKnowledgeBases
    }
  ];

  return (
    <div className="space-y-4">
      {sections.map((section) =>
        section.items.length === 0 ? null : (
          <div key={section.key} className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
              {section.label}
            </p>
            <div className="space-y-2">
              {section.items.map((item) => {
                const itemKey = `${item.scope}:${item.teamId ?? "personal"}:${item.id}`;
                const isSelected = itemKey === selectedKey;

                return (
                  <button
                    key={itemKey}
                    type="button"
                    className={cn(
                      "flex w-full items-start gap-3 rounded-2xl border px-4 py-3 text-left transition-colors",
                      isSelected
                        ? "border-primary/30 bg-primary/5"
                        : "border-border/70 bg-background hover:bg-accent"
                    )}
                    onClick={() => onSelect(item)}
                  >
                    <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-secondary text-muted-foreground">
                      {item.scope === "team" ? (
                        <Users className="h-4 w-4" />
                      ) : (
                        <Database className="h-4 w-4" />
                      )}
                    </div>
                    <div className="min-w-0 space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="truncate text-sm font-medium text-foreground">{item.name}</p>
                        <Badge variant={item.scope === "team" ? "secondary" : "default"}>
                          {item.scope === "team" ? messages.common.team : messages.common.personal}
                        </Badge>
                      </div>
                      <p className="truncate text-xs text-muted-foreground">
                        {item.scope === "team"
                          ? item.teamName || messages.common.teamId(item.teamId ?? 0)
                          : messages.knowledgeBases.workspaceScopePersonal}
                      </p>
                      {item.description ? (
                        <p className="line-clamp-2 text-xs text-muted-foreground">
                          {item.description}
                        </p>
                      ) : null}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        )
      )}
    </div>
  );
}
