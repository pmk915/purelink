"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/hooks/use-i18n";
import {
  createKnowledgeBaseSchema,
  type CreateKnowledgeBaseValues
} from "@/schemas/knowledge-bases";

export function CreateKnowledgeBaseForm({
  title,
  description,
  submitLabel,
  onSubmit,
  isSubmitting
}: {
  title: string;
  description: string;
  submitLabel: string;
  onSubmit: (values: CreateKnowledgeBaseValues) => Promise<void> | void;
  isSubmitting: boolean;
}) {
  const { messages } = useI18n();
  const form = useForm<CreateKnowledgeBaseValues>({
    resolver: zodResolver(createKnowledgeBaseSchema),
    defaultValues: {
      name: "",
      description: ""
    }
  });

  const handleSubmit = form.handleSubmit(async (values) => {
    try {
      await onSubmit(values);
      form.reset();
    } catch (error) {
      form.setError("root", {
        message:
          error instanceof Error ? error.message : messages.knowledgeBases.createError
      });
    }
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <form className="space-y-4" onSubmit={handleSubmit}>
          <div className="space-y-2">
            <Label htmlFor="kb-name">{messages.common.name}</Label>
            <Input id="kb-name" {...form.register("name")} />
            <p className="text-xs text-rose-600">{form.formState.errors.name?.message}</p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="kb-description">{messages.common.description}</Label>
            <Textarea id="kb-description" rows={4} {...form.register("description")} />
          </div>
          {form.formState.errors.root?.message ? (
            <div className="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {form.formState.errors.root.message}
            </div>
          ) : null}
          <Button disabled={isSubmitting}>{isSubmitting ? messages.common.loading : submitLabel}</Button>
        </form>
      </CardContent>
    </Card>
  );
}
