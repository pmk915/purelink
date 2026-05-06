"use client";

import { Button } from "@/components/ui/button";

export type ConfirmDialogProps = {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel,
  destructive = false,
  loading = false,
  onConfirm,
  onCancel
}: ConfirmDialogProps) {
  if (!open) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 px-4"
      onClick={onCancel}
      role="presentation"
    >
      <div
        className="w-full max-w-md rounded-[28px] border border-border/70 bg-white p-6 shadow-soft"
        onClick={(event) => event.stopPropagation()}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-description"
      >
        <div className="space-y-2">
          <h2 id="confirm-dialog-title" className="text-lg font-semibold text-foreground">
            {title}
          </h2>
          {description ? (
            <p id="confirm-dialog-description" className="text-sm leading-6 text-muted-foreground">
              {description}
            </p>
          ) : null}
        </div>

        <div className="mt-6 flex items-center justify-end gap-3">
          <Button variant="ghost" type="button" onClick={onCancel} disabled={loading}>
            {cancelLabel}
          </Button>
          <Button
            variant={destructive ? "destructive" : "default"}
            type="button"
            onClick={onConfirm}
            disabled={loading}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
