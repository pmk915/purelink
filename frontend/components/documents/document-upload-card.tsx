"use client";

import { useRef, useState } from "react";
import { UploadCloud } from "lucide-react";

import { ErrorState } from "@/components/common/error-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useI18n } from "@/hooks/use-i18n";
import { ApiClientError } from "@/lib/api-client";
import type { UploadConstraints } from "@/types";

type UploadItemStatus =
  | "uploading"
  | "queued"
  | "processing"
  | "indexed"
  | "failed"
  | "duplicate"
  | "too_large"
  | "unsupported";

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
const DEFAULT_MAX_UPLOAD_SIZE_MB = 25;
const DEFAULT_UPLOAD_CONSTRAINTS: UploadConstraints = {
  max_upload_size_mb: DEFAULT_MAX_UPLOAD_SIZE_MB,
  max_upload_size_bytes: DEFAULT_MAX_UPLOAD_SIZE_MB * 1024 * 1024,
  allowed_extensions: [...SUPPORTED_EXTENSIONS],
  allowed_mime_types: [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/markdown",
    "text/plain"
  ]
};
const EXTENSION_LABELS: Record<string, string> = {
  ".pdf": "PDF",
  ".docx": "DOCX",
  ".md": "Markdown",
  ".txt": "TXT"
};
const EXTENSION_DISPLAY_ORDER = [".pdf", ".docx", ".md", ".txt"];

function isSupportedDocumentFile(fileName: string, allowedExtensions: string[]) {
  const normalized = fileName.toLowerCase();
  return allowedExtensions.some((extension) => normalized.endsWith(extension.toLowerCase()));
}

function hasInvalidFileName(fileName: string) {
  const normalized = fileName.trim();
  return (
    normalized.length === 0 ||
    normalized.length > 255 ||
    normalized.includes("/") ||
    normalized.includes("\\") ||
    normalized.includes("\0")
  );
}

function formatUploadFormats(extensions: string[]) {
  return extensions
    .map((extension) => extension.toLowerCase())
    .sort((left, right) => {
      const leftIndex = EXTENSION_DISPLAY_ORDER.indexOf(left);
      const rightIndex = EXTENSION_DISPLAY_ORDER.indexOf(right);
      return (leftIndex === -1 ? 99 : leftIndex) - (rightIndex === -1 ? 99 : rightIndex);
    })
    .map((extension) => EXTENSION_LABELS[extension.toLowerCase()] ?? extension.toUpperCase())
    .join(", ");
}

export function DocumentUploadCard({
  title,
  description,
  onUpload,
  isUploading,
  constraints
}: {
  title: string;
  description: string;
  onUpload: (file: File) => Promise<void> | void;
  isUploading: boolean;
  constraints?: UploadConstraints | null;
}) {
  const { messages } = useI18n();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [items, setItems] = useState<UploadItem[]>([]);
  const [localError, setLocalError] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<unknown>(null);
  const uploadConstraints = constraints ?? DEFAULT_UPLOAD_CONSTRAINTS;
  const allowedExtensions =
    uploadConstraints.allowed_extensions.length > 0
      ? uploadConstraints.allowed_extensions
      : [...SUPPORTED_EXTENSIONS];
  const formatLabel = formatUploadFormats(allowedExtensions);
  const acceptValue = [
    ...allowedExtensions.flatMap((extension) => [extension, extension.toUpperCase()]),
    ...uploadConstraints.allowed_mime_types
  ].join(",");

  const updateItem = (id: string, next: Partial<UploadItem>) => {
    setItems((current) =>
      current.map((item) => (item.id === id ? { ...item, ...next } : item))
    );
  };

  function validateSelectedFiles(selectedFiles: File[]) {
    const invalidNameFile = selectedFiles.find((nextFile) =>
      hasInvalidFileName(nextFile.name)
    );
    if (invalidNameFile) {
      return messages.documents.invalidFileName;
    }

    const emptyFile = selectedFiles.find((nextFile) => nextFile.size === 0);
    if (emptyFile) {
      return messages.documents.emptyFile;
    }

    const tooLargeFile = selectedFiles.find(
      (nextFile) => nextFile.size > uploadConstraints.max_upload_size_bytes
    );
    if (tooLargeFile) {
      return messages.documents.fileTooLarge(uploadConstraints.max_upload_size_mb);
    }

    const unsupportedFile = selectedFiles.find(
      (nextFile) => !isSupportedDocumentFile(nextFile.name, allowedExtensions)
    );
    if (unsupportedFile) {
      return messages.documents.unsupportedFileTypeWithFormats(formatLabel);
    }

    return null;
  }

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
          accept={acceptValue}
          onChange={(event) => {
            const selectedFiles = Array.from(event.target.files ?? []);
            const validationError = validateSelectedFiles(selectedFiles);
            if (validationError) {
              setItems([]);
              setLocalError(validationError);
              setUploadError(null);
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
            setLocalError(null);
            setUploadError(null);
          }}
        />
        <p className="text-xs text-muted-foreground">
          {messages.documents.supportedFormatsWithLimit(
            formatLabel,
            uploadConstraints.max_upload_size_mb
          )}
        </p>
        {items.length > 0 ? (
          <div className="space-y-2">
            {items.map((item) => (
              <div key={item.id} className="space-y-1">
                <div className="flex items-center justify-between gap-3 rounded-md bg-secondary/60 px-4 py-3 text-sm text-foreground">
                  <span className="min-w-0 truncate">{item.file.name}</span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {messages.documents.uploadStatuses[item.status]}
                  </span>
                </div>
                {item.message ? (
                  <p className="px-4 text-xs text-muted-foreground">{item.message}</p>
                ) : null}
              </div>
            ))}
          </div>
        ) : null}
        {localError || uploadError ? (
          <ErrorState
            title={localError ?? messages.documents.uploadFailed}
            error={uploadError ?? undefined}
            requestIdLabel={messages.common.requestId}
          />
        ) : null}
        <Button
          disabled={items.length === 0 || isUploading}
          onClick={async () => {
            if (items.length === 0) {
              setLocalError(messages.documents.chooseFileError);
              setUploadError(null);
              return;
            }

            const validationError = validateSelectedFiles(items.map((item) => item.file));
            if (validationError) {
              setLocalError(validationError);
              setUploadError(null);
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
                          (uploadError.errorCode === "FILE_TOO_LARGE" ||
                            uploadError.errorCode === "UPLOAD_TOO_LARGE")
                        ? "too_large"
                        : uploadError instanceof ApiClientError &&
                            uploadError.errorCode === "UNSUPPORTED_FILE_TYPE"
                          ? "unsupported"
                          : "failed";
                  setLocalError(null);
                  setUploadError(uploadError);
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
              ["failed", "duplicate", "too_large", "unsupported"].includes(status)
            );
            if (!hasFailure) {
              setItems([]);
              setLocalError(null);
              setUploadError(null);
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
