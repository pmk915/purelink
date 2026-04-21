"use client";

import Link from "next/link";
import { Menu, Plus } from "lucide-react";

import { useAuth } from "@/hooks/use-auth";
import { useI18n } from "@/hooks/use-i18n";
import { LocaleSwitch } from "@/components/layout/locale-switch";
import { Button } from "@/components/ui/button";

export function TopBar() {
  const { currentUser, logout } = useAuth();
  const { messages } = useI18n();

  return (
    <header className="sticky top-0 z-20 border-b border-border/70 bg-background/80 backdrop-blur">
      <div className="flex items-center gap-4 px-4 py-4 md:px-8">
        <button
          type="button"
          className="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-border/70 bg-white/80 text-muted-foreground md:hidden"
          aria-label={messages.common.openNavigation}
        >
          <Menu className="h-5 w-5" />
        </button>

        <div className="ml-auto flex items-center gap-3">
          <Link
            href="/knowledge-bases"
            className="hidden rounded-2xl border border-border/70 bg-white/80 px-4 py-2.5 text-sm font-medium text-foreground shadow-sm transition hover:bg-white md:inline-flex md:items-center md:gap-2"
          >
            <Plus className="h-4 w-4" />
            {messages.topbar.newKnowledgeBase}
          </Link>
          <LocaleSwitch />
          <div className="rounded-2xl border border-border/70 bg-white/80 px-4 py-2 text-right shadow-sm">
            <p className="text-sm font-medium text-foreground">
              {currentUser?.username ?? messages.common.anonymous}
            </p>
            <p className="text-xs text-muted-foreground">{currentUser?.email ?? ""}</p>
          </div>
          <Button variant="outline" onClick={logout}>
            {messages.common.signOut}
          </Button>
        </div>
      </div>
    </header>
  );
}
