"use client";

import { KnowledgeBaseWorkspace } from "@/components/knowledge-bases/knowledge-base-workspace";

export default function PersonalKnowledgeBaseDetailPage({
  params
}: {
  params: { kbId: string };
}) {
  return (
    <KnowledgeBaseWorkspace
      scope="personal"
      knowledgeBaseId={Number(params.kbId)}
    />
  );
}
