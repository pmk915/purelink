"use client";

import { useRef, useState } from "react";
import { UploadCloud } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useI18n } from "@/hooks/use-i18n";
import { ApiClientError } from "@/lib/api-client";

type UploadItemStatus =
  | "uploading"
  | "queued"
  | "processing"
  | "indexed"
  | "failed"
  | "duplicate"
  | "too_large";

type UploadItem = {
  id: string;
  file: File;
  status: UploadItemStatus;
  message?: string;
};

const SUPPORTED_EXTENSIONS = [
  ".txt",
  ".md",
  ".docx",
  ".pdf"
] as const;

function isSupportedDocumentFile(fileName: string) {
  const normalized = fileName.toLowerCase();
  return SUPPORTED_EXTENSIONS.some((extension) => normalized.endsWith(extension));
}

export function DocumentUploadCard({
  title,
  description,
  onUpload,
  isUploading
}: {
  title: string;
  description: string;
  onUpload: (file: File) => Promise<void> | void;
  isUploading: boolean;
}) {
  const { messages } = useI18n();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [items, setItems] = useState<UploadItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  const updateItem = (id: string, next: Partial<UploadItem>) => {
    setItems((current) =>
      current.map((item) => (item.id === id ? { ...item, ...next } : item))
    );
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Input
          ref={inputRef}
          type="file"
          multiple
          accept=".txt,.TXT,.md,.MD,.docx,.DOCX,.pdf,.PDF,text/plain,text/markdown,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/pdf"
          onChange={(event) => {
            const selectedFiles = Array.from(event.target.files ?? []);
            const unsupportedFile = selectedFiles.find(
              (nextFile) => !isSupportedDocumentFile(nextFile.name)
            );
            if (unsupportedFile) {
              setItems([]);
              setError(messages.documents.unsupportedFileType);
              event.target.value = "";
              return;
            }

            setItems(
              selectedFiles.map((nextFile) => ({
                id: `${nextFile.name}-${nextFile.size}-${nextFile.lastModified}`,
                file: nextFile,
                status: "queued"
              }))
            );
            setError(null);
          }}
        />
        <p className="text-xs text-muted-foreground">{messages.documents.supportedFormats}</p>
        {items.length > 0 ? (
          <div className="space-y-2">
            {items.map((item) => (
              <div
                key={item.id}
                className="flex items-center justify-between gap-3 rounded-md bg-secondary/60 px-4 py-3 text-sm text-foreground"
              >
                <span className="min-w-0 truncate">{item.file.name}</span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {messages.documents.uploadStatuses[item.status]}
                </span>
              </div>
            ))}
          </div>
        ) : null}
        {error ? (
          <div className="rounded-md bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>
        ) : null}
        <Button
          disabled={items.length === 0 || isUploading}
          onClick={async () => {
            if (items.length === 0) {
              setError(messages.documents.chooseFileError);
              return;
            }

            const results = await Promise.all(
              items.map(async (item) => {
                updateItem(item.id, { status: "uploading", message: undefined });
                try {
                  await onUpload(item.file);
                  updateItem(item.id, { status: "queued" });
                  return "queued" as UploadItemStatus;
                } catch (uploadError) {
                  console.error("upload failed", {
                    error: uploadError,
                    file: {
                      name: item.file.name,
                      type: item.file.type,
                      size: item.file.size
                    }
                  });
                  const status =
                    uploadError instanceof ApiClientError &&
                    uploadError.errorCode === "DUPLICATE_DOCUMENT"
                      ? "duplicate"
                      : uploadError instanceof ApiClientError &&
                          uploadError.errorCode === "FILE_TOO_LARGE"
                        ? "too_large"
                        : "failed";
                  updateItem(item.id, {
                    status,
                    message:
                      uploadError instanceof Error
                        ? uploadError.message
                        : messages.documents.uploadFailed
                  });
                  return status;
                }
              })
            );

            const hasFailure = results.some((status) =>
              ["failed", "duplicate", "too_large"].includes(status)
            );
            if (!hasFailure) {
              setItems([]);
              setError(null);
              if (inputRef.current) {
                inputRef.current.value = "";
              }
            }
          }}
        >
          <UploadCloud className="h-4 w-4" />
          {isUploading ? messages.documents.uploading : messages.documents.uploadSubmit}
        </Button>
      </CardContent>
    </Card>
  );
}
