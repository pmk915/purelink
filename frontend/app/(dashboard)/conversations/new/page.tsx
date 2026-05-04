"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueries } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";

import * as teamsApi from "@/api/teams";
import { ConversationSidebar } from "@/components/conversations/conversation-sidebar";
import {
  KnowledgeBaseSelector,
  type AccessibleKnowledgeBaseOption
} from "@/components/knowledge-bases/knowledge-base-selector";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/hooks/use-auth";
import { useConversations } from "@/hooks/use-conversations";
import { useI18n } from "@/hooks/use-i18n";
import { usePersonalDocuments, useTeamDocuments } from "@/hooks/use-documents";
import { usePersonalKnowledgeBases } from "@/hooks/use-knowledge-bases";
import { useAskPersonal, useAskTeam } from "@/hooks/use-qa";
import { useTeams } from "@/hooks/use-teams";
import { askSchema, type AskValues } from "@/schemas/qa";
import type { Document } from "@/types";

function isDocumentQueryable(document: Document) {
  return (
    document.review_status !== "pending_review" &&
    document.review_status !== "rejected" &&
    document.processing_status === "indexed"
  );
}

function isDocumentPreparing(document: Document) {
  if (
    document.review_status === "pending_review" ||
    document.review_status === "rejected"
  ) {
    return false;
  }

  return (
    document.processing_status === "uploaded" ||
    document.processing_status === "processing" ||
    document.processing_status === "parsed" ||
    document.latest_processing_job_status === "queued" ||
    document.latest_processing_job_status === "processing" ||
    document.latest_processing_job_status === "retrying"
  );
}

export default function NewConversationPage() {
  const router = useRouter();
  const { accessToken } = useAuth();
  const { messages } = useI18n();
  const [selectedKnowledgeBase, setSelectedKnowledgeBase] =
    useState<AccessibleKnowledgeBaseOption | null>(null);
  const personalKnowledgeBasesQuery = usePersonalKnowledgeBases(accessToken);
  const teamsQuery = useTeams(accessToken);
  const conversationsQuery = useConversations(accessToken);
  const teamKnowledgeBaseQueries = useQueries({
    queries: (teamsQuery.data ?? []).map((team) => ({
      queryKey: ["knowledge-bases", "team", team.id],
      queryFn: () => teamsApi.listTeamKnowledgeBases(accessToken as string, team.id),
      enabled: Boolean(accessToken)
    }))
  });
  const selectedPersonalDocumentsQuery = usePersonalDocuments(
    accessToken,
    selectedKnowledgeBase?.scope === "personal" ? selectedKnowledgeBase.id : Number.NaN
  );
  const selectedTeamDocumentsQuery = useTeamDocuments(
    accessToken,
    selectedKnowledgeBase?.scope === "team" ? selectedKnowledgeBase.teamId ?? Number.NaN : Number.NaN,
    selectedKnowledgeBase?.scope === "team" ? selectedKnowledgeBase.id : Number.NaN
  );
  const askPersonal = useAskPersonal(
    accessToken,
    selectedKnowledgeBase?.scope === "personal" ? selectedKnowledgeBase.id : Number.NaN
  );
  const askTeam = useAskTeam(
    accessToken,
    selectedKnowledgeBase?.scope === "team" ? selectedKnowledgeBase.teamId ?? Number.NaN : Number.NaN,
    selectedKnowledgeBase?.scope === "team" ? selectedKnowledgeBase.id : Number.NaN
  );

  const askForm = useForm<AskValues>({
    resolver: zodResolver(askSchema),
    defaultValues: {
      question: "",
      top_k: 5,
      conversation_id: null
    }
  });

  const personalOptions = useMemo(
    () =>
      (personalKnowledgeBasesQuery.data ?? []).map((knowledgeBase) => ({
        id: knowledgeBase.id,
        name: knowledgeBase.name,
        description: knowledgeBase.description,
        scope: "personal" as const,
        teamId: null,
        teamName: null
      })),
    [personalKnowledgeBasesQuery.data]
  );
  const teamOptions = useMemo(
    () =>
      (teamsQuery.data ?? []).flatMap((team, index) =>
        (teamKnowledgeBaseQueries[index]?.data ?? []).map((knowledgeBase) => ({
          id: knowledgeBase.id,
          name: knowledgeBase.name,
          description: knowledgeBase.description,
          scope: "team" as const,
          teamId: team.id,
          teamName: team.name
        }))
      ),
    [teamKnowledgeBaseQueries, teamsQuery.data]
  );

  const selectedDocuments =
    selectedKnowledgeBase?.scope === "team"
      ? selectedTeamDocumentsQuery.data ?? []
      : selectedPersonalDocumentsQuery.data ?? [];
  const selectedDocumentsLoading =
    selectedKnowledgeBase?.scope === "team"
      ? selectedTeamDocumentsQuery.isLoading
      : selectedPersonalDocumentsQuery.isLoading;
  const askableDocuments = selectedDocuments.filter(isDocumentQueryable).length;
  const selectedAvailability = !selectedKnowledgeBase
    ? "unselected"
    : selectedDocumentsLoading
      ? "loading"
    : selectedDocuments.length === 0
      ? "empty"
      : askableDocuments > 0
        ? "ready"
        : selectedDocuments.some((document) => document.review_status === "pending_review")
          ? "waiting_review"
          : selectedDocuments.some(isDocumentPreparing)
            ? "preparing"
            : "unavailable";
  const availabilityMessage =
    selectedAvailability === "unselected"
      ? messages.conversations.selectKnowledgeBaseHint
      : selectedAvailability === "loading"
        ? messages.common.loading
      : selectedAvailability === "empty"
        ? messages.qa.noQueryableDocuments
        : selectedAvailability === "waiting_review"
          ? messages.qa.documentsWaitingReview
          : selectedAvailability === "preparing"
            ? messages.qa.documentsPreparing
            : selectedAvailability === "unavailable"
              ? messages.qa.noAvailableDocuments
              : null;

  return (
    <div className="grid gap-6 xl:grid-cols-[300px_minmax(0,1fr)]">
      <div className="xl:sticky xl:top-24 xl:h-[calc(100vh-7rem)]">
        <ConversationSidebar conversations={conversationsQuery.data ?? []} />
      </div>

      <div className="space-y-6">
        <Card className="border-border/70 shadow-card">
          <CardHeader className="space-y-3">
            <CardTitle className="text-3xl">{messages.conversations.newConversationTitle}</CardTitle>
            <CardDescription>{messages.conversations.newConversationDescription}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="space-y-3">
              <p className="text-sm font-medium text-foreground">
                {messages.conversations.selectKnowledgeBase}
              </p>
              <KnowledgeBaseSelector
                personalKnowledgeBases={personalOptions}
                teamKnowledgeBases={teamOptions}
                selectedKey={
                  selectedKnowledgeBase
                    ? `${selectedKnowledgeBase.scope}:${selectedKnowledgeBase.teamId ?? "personal"}:${selectedKnowledgeBase.id}`
                    : null
                }
                onSelect={(item) => setSelectedKnowledgeBase(item)}
                emptyLabel={messages.conversations.noKnowledgeBasesAvailable}
                personalLabel={messages.common.personal}
                teamLabel={messages.common.team}
              />
            </div>

            <form
              className="space-y-4"
              onSubmit={askForm.handleSubmit(async (values) => {
                if (!selectedKnowledgeBase || selectedAvailability !== "ready") {
                  return;
                }

                try {
                  const result =
                    selectedKnowledgeBase.scope === "team" && selectedKnowledgeBase.teamId
                      ? await askTeam.mutateAsync(values)
                      : await askPersonal.mutateAsync(values);
                  router.push(`/conversations/${result.conversation_id}`);
                } catch (error) {
                  console.error("conversation create failed", { error, selectedKnowledgeBase });
                  askForm.setError("root", {
                    message: messages.qa.askFailed
                  });
                }
              })}
            >
              {availabilityMessage ? (
                <div className="rounded-2xl bg-secondary/70 px-4 py-3 text-sm text-muted-foreground">
                  {availabilityMessage}
                </div>
              ) : null}

              <div className="space-y-2">
                <Label htmlFor="new-conversation-question">{messages.qa.askQuestion}</Label>
                <Textarea
                  id="new-conversation-question"
                  rows={6}
                  placeholder={messages.qa.askPlaceholder}
                  disabled={!selectedKnowledgeBase || selectedAvailability !== "ready"}
                  {...askForm.register("question")}
                />
                <p className="text-xs text-rose-600">{askForm.formState.errors.question?.message}</p>
              </div>

              {askForm.formState.errors.root?.message ? (
                <div className="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
                  {askForm.formState.errors.root.message}
                </div>
              ) : null}

              <div className="flex items-center justify-end">
                <Button
                  disabled={
                    askForm.formState.isSubmitting ||
                    !selectedKnowledgeBase ||
                    selectedAvailability !== "ready"
                  }
                >
                  <Sparkles className="h-4 w-4" />
                  {askForm.formState.isSubmitting ? messages.qa.asking : messages.qa.askSubmit}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
