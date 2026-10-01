import { apiFetch, refreshAccessToken, setAccessToken } from "@/lib/api";
import type { CurrentUser, TokenResponse } from "@/types/auth";

export async function login(email: string, password: string): Promise<CurrentUser> {
  const response = await apiFetch<TokenResponse>("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  setAccessToken(response.access_token);
  return response.user;
}

/** Restaure la session après un rechargement de page (cookie HttpOnly). Null si aucune session. */
export async function restoreSession(): Promise<CurrentUser | null> {
  const response = await refreshAccessToken();
  return response?.user ?? null;
}

export async function logout(): Promise<void> {
  try {
    await apiFetch<void>("/auth/logout", { method: "POST" });
  } finally {
    // Même si l'API ne répond pas, le navigateur oublie le jeton
    setAccessToken(null);
  }
}

export function getMe(): Promise<CurrentUser> {
  return apiFetch<CurrentUser>("/auth/me");
}
