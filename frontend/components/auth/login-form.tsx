"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import * as authApi from "@/api/auth";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/hooks/use-auth";
import { useI18n } from "@/hooks/use-i18n";
import { loginSchema, type LoginFormValues } from "@/schemas/auth";

export function LoginForm() {
  const router = useRouter();
  const { setAccessToken } = useAuth();
  const { messages } = useI18n();
  const form = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      identifier: "",
      password: ""
    }
  });

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      const response = await authApi.login(values);
      setAccessToken(response.access_token);
      router.replace("/");
    } catch (error) {
      form.setError("root", {
        message:
          error instanceof Error ? error.message : messages.auth.login.fallbackError
      });
    }
  });

  return (
    <Card className="border-white/60 bg-white/90">
      <CardHeader>
        <CardTitle>{messages.auth.login.title}</CardTitle>
        <CardDescription>{messages.auth.login.description}</CardDescription>
      </CardHeader>
      <CardContent>
        <form className="space-y-5" onSubmit={onSubmit}>
          <div className="space-y-2">
            <Label htmlFor="identifier">{messages.auth.login.identifier}</Label>
            <Input id="identifier" {...form.register("identifier")} />
            <p className="text-xs text-rose-600">{form.formState.errors.identifier?.message}</p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">{messages.auth.login.password}</Label>
            <Input id="password" type="password" {...form.register("password")} />
            <p className="text-xs text-rose-600">{form.formState.errors.password?.message}</p>
          </div>
          {form.formState.errors.root?.message ? (
            <div className="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {form.formState.errors.root.message}
            </div>
          ) : null}
          <Button className="w-full" size="lg" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting
              ? messages.auth.login.submitting
              : messages.auth.login.submit}
          </Button>
          <p className="text-center text-sm text-muted-foreground">
            {messages.auth.login.switchPrompt}{" "}
            <Link href="/register" className="font-medium text-primary">
              {messages.auth.login.switchAction}
            </Link>
          </p>
        </form>
      </CardContent>
    </Card>
  );
}
