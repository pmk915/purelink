"use client";

import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import * as documentApi from "@/api/documents";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/hooks/use-auth";
import { useI18n } from "@/hooks/use-i18n";
import {
  useApproveTeamDocument,
  useRejectTeamDocument,
  useTeamReviewTasks
} from "@/hooks/use-documents";
import { rejectDocumentSchema, type RejectDocumentValues } from "@/schemas/documents";

function RejectForm({
  onReject,
  isSubmitting
}: {
  onReject: (values: RejectDocumentValues) => Promise<void> | void;
  isSubmitting: boolean;
}) {
  const { messages } = useI18n();
  const form = useForm<RejectDocumentValues>({
    resolver: zodResolver(rejectDocumentSchema),
    defaultValues: {
      review_comment: ""
    }
  });

  return (
    <form
      className="space-y-3"
      onSubmit={form.handleSubmit(async (values) => {
        try {
          await onReject(values);
          form.reset();
        } catch (error) {
          form.setError("root", {
            message: error instanceof Error ? error.message : messages.reviews.rejectError
          });
        }
      })}
    >
      <div className="space-y-2">
        <Label>{messages.reviews.rejectReason}</Label>
        <Textarea rows={3} {...form.register("review_comment")} />
        <p className="text-xs text-rose-600">{form.formState.errors.review_comment?.message}</p>
      </div>
      {form.formState.errors.root?.message ? (
        <div className="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {form.formState.errors.root.message}
        </div>
      ) : null}
      <Button variant="destructive" disabled={isSubmitting}>
        {isSubmitting ? messages.reviews.rejecting : messages.reviews.rejectSubmit}
      </Button>
    </form>
  );
}

export default function TeamReviewsPage({
  params
}: {
  params: { teamId: string };
}) {
  const teamId = Number(params.teamId);
  const { accessToken } = useAuth();
  const { messages } = useI18n();
  const [activeDocumentId, setActiveDocumentId] = useState<number | null>(null);
  const [approvalError, setApprovalError] = useState<string | null>(null);
  const reviewsQuery = useTeamReviewTasks(accessToken, teamId);
  const approveMutation = useApproveTeamDocument(accessToken, teamId);
  const rejectMutation = useRejectTeamDocument(accessToken, teamId);

  return (
    <div className="space-y-6">
      <Card className="bg-gradient-to-br from-white via-indigo-50 to-sky-50">
        <CardHeader>
          <CardDescription>{messages.reviews.label}</CardDescription>
          <CardTitle className="text-3xl">{messages.reviews.title}</CardTitle>
        </CardHeader>
        <CardContent className="text-sm leading-7 text-muted-foreground">
          {messages.reviews.description}
        </CardContent>
      </Card>

      <div className="grid gap-4">
        {(reviewsQuery.data ?? []).map((document) => (
          <Card key={document.id}>
            <CardHeader>
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <CardTitle>{document.original_filename}</CardTitle>
                  <CardDescription className="mt-2">
                    {messages.common.submittedBy(document.submitted_by)} ·{" "}
                    {messages.common.knowledgeBaseId(document.knowledge_base_id)}
                  </CardDescription>
                </div>
                <Badge variant="warning">{messages.documents.statusPendingReview}</Badge>
              </div>
            </CardHeader>
            <CardContent className="grid gap-6 lg:grid-cols-[220px_minmax(0,1fr)]">
              <div className="space-y-3">
                <Button
                  className="w-full"
                  disabled={approveMutation.isPending}
                  onClick={async () => {
                    try {
                      setActiveDocumentId(document.id);
                      setApprovalError(null);
                      const approvedDocument = await approveMutation.mutateAsync(document.id);
                      if (accessToken) {
                        try {
                          await documentApi.processTeamDocument(
                            accessToken,
                            teamId,
                            approvedDocument.knowledge_base_id,
                            approvedDocument.id
                          );
                        } catch (error) {
                          console.error("automatic document preparation failed", { error });
                          setApprovalError(messages.reviews.autoPrepareError);
                        }
                      }
                    } catch (error) {
                      console.error("document approval failed", { error });
                      setApprovalError(messages.reviews.approveError);
                    }
                  }}
                >
                  {approveMutation.isPending && activeDocumentId === document.id
                    ? messages.reviews.approving
                    : messages.reviews.approveSubmit}
                </Button>
                <p className="text-xs text-muted-foreground">
                  {messages.reviews.approvalNote}
                </p>
                {approvalError && activeDocumentId === document.id ? (
                  <p className="text-xs text-rose-600">{approvalError}</p>
                ) : null}
              </div>
              <RejectForm
                isSubmitting={rejectMutation.isPending && activeDocumentId === document.id}
                onReject={async (values) => {
                  setActiveDocumentId(document.id);
                  await rejectMutation.mutateAsync({
                    documentId: document.id,
                    review_comment: values.review_comment
                  });
                }}
              />
            </CardContent>
          </Card>
        ))}

        {reviewsQuery.data?.length === 0 ? (
          <Card>
            <CardContent className="pt-6 text-sm text-muted-foreground">
              {messages.reviews.empty}
            </CardContent>
          </Card>
        ) : null}
      </div>
    </div>
  );
}
