"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import * as authApi from "@/api/auth";
import {
  clearStoredAccessToken,
  getStoredAccessToken,
  storeAccessToken
} from "@/lib/auth";
import type { User } from "@/types";

type AuthContextValue = {
  accessToken: string | null;
  currentUser: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  setAccessToken: (token: string) => void;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [accessToken, setAccessTokenState] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setAccessTokenState(getStoredAccessToken());
    setHydrated(true);
  }, []);

  const currentUserQuery = useQuery({
    queryKey: ["auth", "me", accessToken],
    queryFn: () => authApi.getCurrentUser(accessToken as string),
    enabled: hydrated && Boolean(accessToken),
    retry: false
  });

  useEffect(() => {
    if (currentUserQuery.error) {
      clearStoredAccessToken();
      setAccessTokenState(null);
    }
  }, [currentUserQuery.error]);

  const setAccessToken = useCallback(
    (token: string) => {
      storeAccessToken(token);
      setAccessTokenState(token);
      void queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
    },
    [queryClient]
  );

  const logout = useCallback(() => {
    clearStoredAccessToken();
    setAccessTokenState(null);
    void queryClient.clear();
  }, [queryClient]);

  const value = useMemo<AuthContextValue>(
    () => ({
      accessToken,
      currentUser: currentUserQuery.data ?? null,
      isAuthenticated: hydrated && Boolean(accessToken) && Boolean(currentUserQuery.data),
      isLoading: !hydrated || currentUserQuery.isLoading,
      setAccessToken,
      logout
    }),
    [accessToken, currentUserQuery.data, currentUserQuery.isLoading, hydrated, logout, setAccessToken]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider.");
  }
  return context;
}
