"use client";

import { KnowledgeBaseWorkspace } from "@/components/knowledge-bases/knowledge-base-workspace";

export default function TeamKnowledgeBaseDetailPage({
  params
}: {
  params: { teamId: string; kbId: string };
}) {
  return (
    <KnowledgeBaseWorkspace
      scope="team"
      teamId={Number(params.teamId)}
      knowledgeBaseId={Number(params.kbId)}
    />
  );
}
