"use client";

import { DocumentPreviewWorkspace } from "@/components/documents/document-preview-workspace";

export default function PersonalDocumentPreviewPage({
  params
}: {
  params: { kbId: string; documentId: string };
}) {
  return (
    <DocumentPreviewWorkspace
      scope="personal"
      knowledgeBaseId={Number(params.kbId)}
      documentId={Number(params.documentId)}
    />
  );
}
