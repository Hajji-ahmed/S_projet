import type { TokenResponse } from "@/types/auth";

/** URL de l'API vue depuis le navigateur (voir NEXT_PUBLIC_API_URL dans .env.example). */
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

export const REFRESH_PATH = "/auth/refresh";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

// --- Jeton d'accès -------------------------------------------------------------------------------
// Gardé en mémoire uniquement (jamais dans localStorage) : un script injecté ne peut pas le voler
// durablement. Après un rechargement de page, la session est restaurée par le cookie HttpOnly.

let accessToken: string | null = null;
let refreshInFlight: Promise<TokenResponse | null> | null = null;
let onTokenRefreshed: ((response: TokenResponse) => void) | null = null;
let onSessionExpired: (() => void) | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function getAccessToken() {
  return accessToken;
}

/** Branché par l'AuthProvider : utilisateur mis à jour après un rafraîchissement, ou session perdue. */
export function setSessionHandlers(handlers: {
  onTokenRefreshed: ((response: TokenResponse) => void) | null;
  onSessionExpired: (() => void) | null;
}) {
  onTokenRefreshed = handlers.onTokenRefreshed;
  onSessionExpired = handlers.onSessionExpired;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // corps vide ou non JSON : message générique ci-dessous
  }
  return response.statusText || "Une erreur est survenue.";
}

/**
 * Demande un nouveau jeton grâce au cookie de session. Plusieurs appels simultanés partagent la même
 * requête. Retourne null si la session n'est plus valable.
 */
export function refreshAccessToken(): Promise<TokenResponse | null> {
  refreshInFlight ??= (async () => {
    try {
      const response = await fetch(`${API_URL}${REFRESH_PATH}`, {
        method: "POST",
        credentials: "include",
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      if (!response.ok) {
        setAccessToken(null);
        return null;
      }
      const body = (await response.json()) as TokenResponse;
      setAccessToken(body.access_token);
      onTokenRefreshed?.(body);
      return body;
    } catch {
      return null;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

function send(path: string, init: RequestInit): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  return fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    // Nécessaire pour envoyer et recevoir le cookie de session (routes /auth)
    credentials: "include",
    cache: "no-store",
  });
}

/**
 * Client HTTP unique vers FastAPI. Le frontend ne parle jamais à PostgreSQL : tout passe par ici,
 * via les wrappers de `services/`.
 *
 * Sur un 401, un seul rafraîchissement du jeton est tenté, puis la requête est rejouée une fois.
 * Si la session est perdue, `onSessionExpired` renvoie vers la page de connexion.
 */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await request(path, init);
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/** Fichier renvoyé par l'API (export Excel...), avec les mêmes règles de session qu'`apiFetch`. */
export async function apiDownload(path: string): Promise<Blob> {
  return (await request(path, {})).blob();
}

async function request(path: string, init: RequestInit): Promise<Response> {
  let response = await send(path, init);

  const canRetry = path !== REFRESH_PATH && !path.startsWith("/auth/login");
  if (response.status === 401 && canRetry) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      response = await send(path, init);
    }
    if (response.status === 401) {
      onSessionExpired?.();
    }
  }

  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response));
  }
  return response;
}
