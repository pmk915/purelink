"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/hooks/use-i18n";
import { createTeamSchema, type CreateTeamValues } from "@/schemas/teams";

export function CreateTeamForm({
  onSubmit,
  isSubmitting
}: {
  onSubmit: (values: CreateTeamValues) => Promise<void> | void;
  isSubmitting: boolean;
}) {
  const { messages } = useI18n();
  const form = useForm<CreateTeamValues>({
    resolver: zodResolver(createTeamSchema),
    defaultValues: {
      name: "",
      description: ""
    }
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>{messages.teams.createTitle}</CardTitle>
        <CardDescription>{messages.teams.createDescription}</CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="space-y-4"
          onSubmit={form.handleSubmit(async (values) => {
            try {
              await onSubmit(values);
              form.reset();
            } catch (error) {
              form.setError("root", {
                message: error instanceof Error ? error.message : messages.teams.createError
              });
            }
          })}
        >
          <div className="space-y-2">
            <Label htmlFor="team-name">{messages.common.name}</Label>
            <Input id="team-name" {...form.register("name")} />
            <p className="text-xs text-rose-600">{form.formState.errors.name?.message}</p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="team-description">{messages.common.description}</Label>
            <Textarea id="team-description" rows={4} {...form.register("description")} />
          </div>
          {form.formState.errors.root?.message ? (
            <div className="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {form.formState.errors.root.message}
            </div>
          ) : null}
          <Button disabled={isSubmitting}>
            {isSubmitting ? messages.teams.creating : messages.teams.createSubmit}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
