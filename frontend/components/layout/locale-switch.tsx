"use client";

import { useI18n } from "@/hooks/use-i18n";
import { cn } from "@/lib/utils";

export function LocaleSwitch({ className }: { className?: string }) {
  const { locale, setLocale, messages } = useI18n();

  return (
    <div
      aria-label={messages.common.language}
      className={cn(
        "flex items-center gap-1 rounded-2xl border border-border/70 bg-white/80 p-1 shadow-sm",
        className
      )}
      role="group"
    >
      <button
        type="button"
        onClick={() => setLocale("en")}
        className={`rounded-xl px-3 py-2 text-sm font-medium transition ${
          locale === "en" ? "bg-primary text-primary-foreground" : "text-muted-foreground"
        }`}
      >
        EN
      </button>
      <button
        type="button"
        onClick={() => setLocale("zh")}
        className={`rounded-xl px-3 py-2 text-sm font-medium transition ${
          locale === "zh" ? "bg-primary text-primary-foreground" : "text-muted-foreground"
        }`}
      >
        中文
      </button>
    </div>
  );
}
