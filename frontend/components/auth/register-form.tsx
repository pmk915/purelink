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
import { registerSchema, type RegisterFormValues } from "@/schemas/auth";

export function RegisterForm() {
  const router = useRouter();
  const { setAccessToken } = useAuth();
  const { messages } = useI18n();
  const form = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      email: "",
      username: "",
      password: ""
    }
  });

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      await authApi.register(values);
      const loginResponse = await authApi.login({
        identifier: values.email,
        password: values.password
      });
      setAccessToken(loginResponse.access_token);
      router.replace("/");
    } catch (error) {
      form.setError("root", {
        message:
          error instanceof Error ? error.message : messages.auth.register.fallbackError
      });
    }
  });

  return (
    <Card className="border-white/60 bg-white/90">
      <CardHeader>
        <CardTitle>{messages.auth.register.title}</CardTitle>
        <CardDescription>{messages.auth.register.description}</CardDescription>
      </CardHeader>
      <CardContent>
        <form className="space-y-5" onSubmit={onSubmit}>
          <div className="space-y-2">
            <Label htmlFor="email">{messages.auth.register.email}</Label>
            <Input id="email" type="email" {...form.register("email")} />
            <p className="text-xs text-rose-600">{form.formState.errors.email?.message}</p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="username">{messages.auth.register.username}</Label>
            <Input id="username" {...form.register("username")} />
            <p className="text-xs text-rose-600">{form.formState.errors.username?.message}</p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">{messages.auth.register.password}</Label>
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
              ? messages.auth.register.submitting
              : messages.auth.register.submit}
          </Button>
          <p className="text-center text-sm text-muted-foreground">
            {messages.auth.register.switchPrompt}{" "}
            <Link href="/login" className="font-medium text-primary">
              {messages.auth.register.switchAction}
            </Link>
          </p>
        </form>
      </CardContent>
    </Card>
  );
}
