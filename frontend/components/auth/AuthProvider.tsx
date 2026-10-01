"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { setSessionHandlers } from "@/lib/api";
import * as authService from "@/services/auth";
import type { CurrentUser } from "@/types/auth";

type AuthState =
  | { status: "loading"; user: null }
  | { status: "authenticated"; user: CurrentUser }
  | { status: "anonymous"; user: null };

type AuthContextValue = AuthState & {
  login: (email: string, password: string) => Promise<CurrentUser>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

const ANONYMOUS: AuthState = { status: "anonymous", user: null };

/**
 * Session de l'utilisateur. Au chargement de la page, la session est restaurée par le cookie HttpOnly
 * (le jeton d'accès, lui, n'est gardé qu'en mémoire).
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading", user: null });

  useEffect(() => {
    setSessionHandlers({
      onTokenRefreshed: (response) => setState({ status: "authenticated", user: response.user }),
      onSessionExpired: () => setState(ANONYMOUS),
    });

    let cancelled = false;
    authService.restoreSession().then((user) => {
      if (!cancelled) setState(user ? { status: "authenticated", user } : ANONYMOUS);
    });

    return () => {
      cancelled = true;
      setSessionHandlers({ onTokenRefreshed: null, onSessionExpired: null });
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const user = await authService.login(email, password);
    setState({ status: "authenticated", user });
    return user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await authService.logout();
    } finally {
      setState(ANONYMOUS);
    }
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, login, logout }}>{children}</AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth doit être utilisé dans un <AuthProvider>.");
  return context;
}
