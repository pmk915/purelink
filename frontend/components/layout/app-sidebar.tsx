"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BookCopy,
  BotMessageSquare,
  Building2,
  Home,
  ShieldCheck
} from "lucide-react";

import { cn } from "@/lib/utils";
import { useI18n } from "@/hooks/use-i18n";

export function AppSidebar() {
  const pathname = usePathname();
  const { messages } = useI18n();

  const navItems = [
    { href: "/", label: messages.nav.dashboard, icon: Home },
    {
      href: "/knowledge-bases",
      label: messages.nav.knowledgeBases,
      icon: BookCopy
    },
    { href: "/teams", label: messages.nav.teams, icon: Building2 },
    {
      href: "/conversations",
      label: messages.nav.conversations,
      icon: BotMessageSquare
    }
  ];

  return (
    <aside className="sticky top-0 hidden h-screen w-72 shrink-0 flex-col border-r border-border/70 bg-white/70 px-5 py-6 backdrop-blur md:flex">
      <Link href="/" className="rounded-3xl bg-white/90 p-5 shadow-card">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/12 text-primary">
            <ShieldCheck className="h-6 w-6" />
          </div>
          <div>
            <p className="text-lg font-semibold tracking-tight">PureLink</p>
            <p className="text-sm text-muted-foreground">{messages.nav.brandSubtitle}</p>
          </div>
        </div>
      </Link>

      <nav className="mt-8 flex flex-1 flex-col gap-2">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active =
            item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);

          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-2xl px-4 py-3 text-sm transition-colors",
                active
                  ? "bg-primary text-primary-foreground shadow-soft"
                  : "text-muted-foreground hover:bg-white/80 hover:text-foreground"
              )}
            >
              <Icon className="h-4 w-4" />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
