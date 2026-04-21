"use client";

import { KnowledgeBaseCard } from "@/components/knowledge-bases/knowledge-base-card";
import { CreateKnowledgeBaseForm } from "@/components/knowledge-bases/create-knowledge-base-form";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/hooks/use-auth";
import { useI18n } from "@/hooks/use-i18n";
import {
  useCreatePersonalKnowledgeBase,
  usePersonalKnowledgeBases
} from "@/hooks/use-knowledge-bases";

export default function KnowledgeBasesPage() {
  const { accessToken } = useAuth();
  const { messages } = useI18n();
  const knowledgeBasesQuery = usePersonalKnowledgeBases(accessToken);
  const createMutation = useCreatePersonalKnowledgeBase(accessToken);

  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
        <CreateKnowledgeBaseForm
          title={messages.knowledgeBases.createTitle}
          description={messages.knowledgeBases.createDescription}
          submitLabel={messages.common.create}
          onSubmit={async (values) => {
            await createMutation.mutateAsync(values);
          }}
          isSubmitting={createMutation.isPending}
        />

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
            <div className="grid gap-4 lg:grid-cols-2">
              {(knowledgeBasesQuery.data ?? []).map((knowledgeBase) => (
                <KnowledgeBaseCard
                  key={knowledgeBase.id}
                  knowledgeBase={knowledgeBase}
                  href={`/knowledge-bases/${knowledgeBase.id}`}
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
      </div>
    </div>
  );
}
