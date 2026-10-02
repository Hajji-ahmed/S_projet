import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  API_URL,
  ApiError,
  apiDownload,
  apiFetch,
  getAccessToken,
  refreshAccessToken,
  setAccessToken,
  setSessionHandlers,
} from "./api";

const USER = {
  id: 1,
  nom: "Salma",
  email: "s@example.com",
  roles: ["Trésorerie"],
  permissions: [],
};

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const tokenResponse = (token: string) =>
  json(200, { access_token: token, token_type: "bearer", expires_in: 900, user: USER });

const fetchMock = vi.fn<typeof fetch>();

function calledUrls(): string[] {
  return fetchMock.mock.calls.map(([url]) => String(url).replace(API_URL, ""));
}

function authorizationOf(call: number): string | null {
  return new Headers(fetchMock.mock.calls[call][1]?.headers).get("Authorization");
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  setAccessToken(null);
  setSessionHandlers({ onTokenRefreshed: null, onSessionExpired: null });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiFetch", () => {
  it("envoie le jeton d'accès et le cookie", async () => {
    setAccessToken("jeton-1");
    fetchMock.mockResolvedValueOnce(json(200, { ok: true }));

    await expect(apiFetch("/auth/me")).resolves.toEqual({ ok: true });

    expect(authorizationOf(0)).toBe("Bearer jeton-1");
    expect(fetchMock.mock.calls[0][1]?.credentials).toBe("include");
  });

  it("sur un 401, rafraîchit une fois puis rejoue la requête avec le nouveau jeton", async () => {
    setAccessToken("expire");
    fetchMock
      .mockResolvedValueOnce(json(401, { detail: "Session expirée." }))
      .mockResolvedValueOnce(tokenResponse("neuf"))
      .mockResolvedValueOnce(json(200, { ok: true }));

    await expect(apiFetch("/banks")).resolves.toEqual({ ok: true });

    expect(calledUrls()).toEqual(["/banks", "/auth/refresh", "/banks"]);
    expect(authorizationOf(2)).toBe("Bearer neuf");
    expect(getAccessToken()).toBe("neuf");
  });

  it("si la session est perdue, prévient l'application et renvoie l'erreur 401", async () => {
    const onSessionExpired = vi.fn();
    setSessionHandlers({ onTokenRefreshed: null, onSessionExpired });
    setAccessToken("expire");
    fetchMock
      .mockResolvedValueOnce(json(401, { detail: "Session expirée." }))
      .mockResolvedValueOnce(json(401, { detail: "Session expirée." }));

    const error = await apiFetch("/banks").catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(401);
    expect(onSessionExpired).toHaveBeenCalledOnce();
    expect(getAccessToken()).toBeNull();
    expect(calledUrls()).toEqual(["/banks", "/auth/refresh"]);
  });

  it("ne tente pas de rafraîchissement sur un échec de connexion", async () => {
    fetchMock.mockResolvedValueOnce(json(401, { detail: "Email ou mot de passe incorrect." }));

    await expect(apiFetch("/auth/login", { method: "POST" })).rejects.toThrow(
      "Email ou mot de passe incorrect.",
    );
    expect(calledUrls()).toEqual(["/auth/login"]);
  });

  it("une erreur 403 n'entraîne ni rafraîchissement ni déconnexion", async () => {
    const onSessionExpired = vi.fn();
    setSessionHandlers({ onTokenRefreshed: null, onSessionExpired });
    fetchMock.mockResolvedValueOnce(json(403, { detail: "Permission requise : banks.manage." }));

    await expect(apiFetch("/banks")).rejects.toMatchObject({
      status: 403,
      message: "Permission requise : banks.manage.",
    });
    expect(onSessionExpired).not.toHaveBeenCalled();
    expect(calledUrls()).toEqual(["/banks"]);
  });

  it("retourne undefined pour une réponse 204", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));

    await expect(apiFetch("/auth/logout", { method: "POST" })).resolves.toBeUndefined();
  });

  it("garde un message générique si l'erreur n'a pas de détail", async () => {
    fetchMock.mockResolvedValueOnce(new Response("oups", { status: 500, statusText: "" }));

    await expect(apiFetch("/health")).rejects.toThrow("Une erreur est survenue.");
  });
});

describe("apiDownload", () => {
  it("renvoie le fichier, après un rafraîchissement du jeton si besoin", async () => {
    setAccessToken("expire");
    fetchMock
      .mockResolvedValueOnce(json(401, { detail: "Session expirée." }))
      .mockResolvedValueOnce(tokenResponse("neuf"))
      .mockResolvedValueOnce(new Response("contenu", { status: 200 }));

    const blob = await apiDownload("/statements/1/export");

    expect(await blob.text()).toBe("contenu");
    expect(calledUrls()).toEqual(["/statements/1/export", "/auth/refresh", "/statements/1/export"]);
    expect(authorizationOf(2)).toBe("Bearer neuf");
  });

  it("renvoie l'erreur de l'API", async () => {
    fetchMock.mockResolvedValueOnce(json(404, { detail: "Relevé introuvable." }));

    await expect(apiDownload("/statements/9/export")).rejects.toThrow("Relevé introuvable.");
  });
});

describe("refreshAccessToken", () => {
  it("plusieurs 401 simultanés ne déclenchent qu'un seul rafraîchissement", async () => {
    setAccessToken("expire");
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/auth/refresh")) return tokenResponse("neuf");
      const auth = new Headers(init?.headers).get("Authorization");
      return auth === "Bearer neuf" ? json(200, { url }) : json(401, {});
    });

    await Promise.all([apiFetch("/a"), apiFetch("/b"), apiFetch("/c")]);

    expect(calledUrls().filter((url) => url === "/auth/refresh")).toHaveLength(1);
  });

  it("informe l'application du nouvel utilisateur", async () => {
    const onTokenRefreshed = vi.fn();
    setSessionHandlers({ onTokenRefreshed, onSessionExpired: null });
    fetchMock.mockResolvedValueOnce(tokenResponse("neuf"));

    await refreshAccessToken();

    expect(onTokenRefreshed).toHaveBeenCalledWith(expect.objectContaining({ user: USER }));
  });

  it("retourne null si l'API est injoignable", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));

    await expect(refreshAccessToken()).resolves.toBeNull();
  });
});
