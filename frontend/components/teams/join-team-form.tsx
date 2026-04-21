"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useI18n } from "@/hooks/use-i18n";
import { joinTeamSchema, type JoinTeamValues } from "@/schemas/teams";

export function JoinTeamForm({
  onSubmit,
  isSubmitting
}: {
  onSubmit: (values: JoinTeamValues) => Promise<void> | void;
  isSubmitting: boolean;
}) {
  const { messages } = useI18n();
  const form = useForm<JoinTeamValues>({
    resolver: zodResolver(joinTeamSchema),
    defaultValues: {
      code: ""
    }
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>{messages.teams.joinTitle}</CardTitle>
        <CardDescription>{messages.teams.joinDescription}</CardDescription>
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
                message: error instanceof Error ? error.message : messages.teams.joinError
              });
            }
          })}
        >
          <div className="space-y-2">
            <Label htmlFor="invite-code">{messages.common.inviteCode}</Label>
            <Input id="invite-code" {...form.register("code")} />
            <p className="text-xs text-rose-600">{form.formState.errors.code?.message}</p>
          </div>
          {form.formState.errors.root?.message ? (
            <div className="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {form.formState.errors.root.message}
            </div>
          ) : null}
          <Button variant="secondary" disabled={isSubmitting}>
            {isSubmitting ? messages.teams.joining : messages.teams.joinSubmit}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
