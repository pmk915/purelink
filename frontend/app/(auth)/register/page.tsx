"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { RegisterForm } from "@/components/auth/register-form";
import { useAuth } from "@/hooks/use-auth";

export default function RegisterPage() {
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      router.replace("/");
    }
  }, [isAuthenticated, isLoading, router]);

  return <div className="w-full max-w-md"><RegisterForm /></div>;
}
