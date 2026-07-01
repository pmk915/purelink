import { LoaderCircle } from "lucide-react";

import { cn } from "@/lib/utils";

export function LoadingState({
  message,
  className
}: {
  message: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-2xl bg-secondary/60 px-4 py-6 text-sm text-muted-foreground",
        className
      )}
    >
      <LoaderCircle className="h-4 w-4 animate-spin" />
      {message}
    </div>
  );
}
