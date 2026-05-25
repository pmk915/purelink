"use client";

import { useState } from "react";

import { KnowledgeBaseCard } from "@/components/knowledge-bases/knowledge-base-card";
import { CreateKnowledgeBaseForm } from "@/components/knowledge-bases/create-knowledge-base-form";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useAuth } from "@/hooks/use-auth";
import { useI18n } from "@/hooks/use-i18n";
import {
  useCreatePersonalKnowledgeBase,
  useDeletePersonalKnowledgeBase,
  usePersonalKnowledgeBases
} from "@/hooks/use-knowledge-bases";
import type { KnowledgeBase } from "@/types";

export default function KnowledgeBasesPage() {
  const { accessToken } = useAuth();
  const { messages } = useI18n();
  const [pendingDeleteKnowledgeBase, setPendingDeleteKnowledgeBase] =
    useState<KnowledgeBase | null>(null);
  const [deleteFeedback, setDeleteFeedback] = useState<string | null>(null);
  const knowledgeBasesQuery = usePersonalKnowledgeBases(accessToken);
  const createMutation = useCreatePersonalKnowledgeBase(accessToken);
  const deleteMutation = useDeletePersonalKnowledgeBase(accessToken);

  return (
    <div className="space-y-6">
      <ConfirmDialog
        open={pendingDeleteKnowledgeBase !== null}
        title={messages.knowledgeBases.deleteDialogTitle}
        description={
          pendingDeleteKnowledgeBase
            ? messages.knowledgeBases.deleteDialogDescription(pendingDeleteKnowledgeBase.name)
            : undefined
        }
        cancelLabel={messages.common.cancel}
        confirmLabel={
          deleteMutation.isPending ? messages.common.deleting : messages.common.delete
        }
        destructive
        loading={deleteMutation.isPending}
        onCancel={() => setPendingDeleteKnowledgeBase(null)}
        onConfirm={async () => {
          if (!pendingDeleteKnowledgeBase) {
            return;
          }
          try {
            await deleteMutation.mutateAsync(pendingDeleteKnowledgeBase.id);
            setDeleteFeedback(messages.knowledgeBases.deleteSucceeded(pendingDeleteKnowledgeBase.name));
            setPendingDeleteKnowledgeBase(null);
          } catch (error) {
            console.error("knowledge base delete failed", {
              error,
              knowledgeBaseId: pendingDeleteKnowledgeBase.id
            });
            setDeleteFeedback(messages.knowledgeBases.deleteFailed);
          }
        }}
      />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Card>
          <CardHeader>
            <CardTitle>{messages.knowledgeBases.title}</CardTitle>
            <CardDescription>{messages.knowledgeBases.description}</CardDescription>
          </CardHeader>
          <CardContent>
            {knowledgeBasesQuery.isLoading ? (
              <p className="text-sm text-muted-foreground">{messages.knowledgeBases.loading}</p>
            ) : null}
            {knowledgeBasesQuery.error ? (
              <div className="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
                {knowledgeBasesQuery.error instanceof Error
                  ? knowledgeBasesQuery.error.message
                  : messages.knowledgeBases.loadError}
              </div>
            ) : null}
            {deleteFeedback ? (
              <div className="mb-4 rounded-2xl bg-secondary/70 px-4 py-3 text-sm text-muted-foreground">
                {deleteFeedback}
              </div>
            ) : null}
            <div className="grid gap-4 lg:grid-cols-2">
              {(knowledgeBasesQuery.data ?? []).map((knowledgeBase) => (
                <KnowledgeBaseCard
                  key={knowledgeBase.id}
                  knowledgeBase={knowledgeBase}
                  href={`/knowledge-bases/${knowledgeBase.id}`}
                  canDelete
                  onDelete={() => setPendingDeleteKnowledgeBase(knowledgeBase)}
                />
              ))}
            </div>
            {knowledgeBasesQuery.data?.length === 0 ? (
              <div className="rounded-3xl bg-secondary/60 p-6 text-sm text-muted-foreground">
                {messages.knowledgeBases.empty}
              </div>
            ) : null}
          </CardContent>
        </Card>

        <CreateKnowledgeBaseForm
          title={messages.knowledgeBases.createTitle}
          description={messages.knowledgeBases.createDescription}
          submitLabel={messages.common.create}
          onSubmit={async (values) => {
            await createMutation.mutateAsync(values);
          }}
          isSubmitting={createMutation.isPending}
        />
      </div>
    </div>
  );
}
