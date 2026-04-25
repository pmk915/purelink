"use client";

import { DocumentPreviewWorkspace } from "@/components/documents/document-preview-workspace";

export default function TeamDocumentPreviewPage({
  params
}: {
  params: { teamId: string; kbId: string; documentId: string };
}) {
  return (
    <DocumentPreviewWorkspace
      scope="team"
      teamId={Number(params.teamId)}
      knowledgeBaseId={Number(params.kbId)}
      documentId={Number(params.documentId)}
    />
  );
}
