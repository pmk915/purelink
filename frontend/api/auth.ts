import { apiClient } from "@/lib/api-client";
import type { TokenResponse, User } from "@/types";

export function register(payload: {
  email: string;
  username: string;
  password: string;
}) {
  return apiClient.post<User>("/auth/register", payload);
}

export function login(payload: { identifier: string; password: string }) {
  return apiClient.post<TokenResponse>("/auth/login", payload);
}

export function getCurrentUser(token: string) {
  return apiClient.get<User>("/users/me", token);
}
