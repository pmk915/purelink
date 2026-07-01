import { Inbox } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function EmptyState({
  title,
  message,
  actionLabel,
  onAction,
  className
}: {
  title: string;
  message?: string;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-border/70 bg-secondary/50 px-4 py-5 text-sm text-muted-foreground",
        className
      )}
    >
      <div className="flex gap-3">
        <Inbox className="mt-0.5 h-4 w-4 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="font-medium text-foreground">{title}</p>
          {message ? <p className="mt-1 leading-6">{message}</p> : null}
          {actionLabel && onAction ? (
            <Button type="button" size="sm" variant="outline" className="mt-3" onClick={onAction}>
              {actionLabel}
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
