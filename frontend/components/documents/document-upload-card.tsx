"use client";

import { useRef, useState } from "react";
import { UploadCloud } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useI18n } from "@/hooks/use-i18n";

const SUPPORTED_EXTENSIONS = [".txt", ".md"] as const;

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
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

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
          accept=".txt,.TXT,.md,.MD,text/plain,text/markdown"
          onChange={(event) => {
            const nextFile = event.target.files?.[0] ?? null;
            if (nextFile && !isSupportedDocumentFile(nextFile.name)) {
              setFile(null);
              setError(messages.documents.unsupportedFileType);
              event.target.value = "";
              return;
            }

            setFile(nextFile);
            setError(null);
          }}
        />
        <p className="text-xs text-muted-foreground">{messages.documents.supportedFormats}</p>
        {file ? (
          <div className="rounded-2xl bg-secondary/60 px-4 py-3 text-sm text-foreground">
            {file.name}
          </div>
        ) : null}
        {error ? (
          <div className="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>
        ) : null}
        <Button
          disabled={!file || isUploading}
          onClick={async () => {
            if (!file) {
              setError(messages.documents.chooseFileError);
              return;
            }
            try {
              await onUpload(file);
              setFile(null);
              setError(null);
              if (inputRef.current) {
                inputRef.current.value = "";
              }
            } catch (uploadError) {
              console.error("upload failed", {
                error: uploadError,
                file: {
                  name: file.name,
                  type: file.type,
                  size: file.size
                }
              });
              setError(
                uploadError instanceof Error ? uploadError.message : messages.documents.uploadFailed
              );
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
