/** URL de l'API vue depuis le navigateur (voir NEXT_PUBLIC_API_URL dans .env.example). */
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/**
 * Client HTTP unique vers FastAPI. Le frontend ne parle jamais à PostgreSQL :
 * tout passe par ici, via les wrappers de `services/`.
 */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { Accept: "application/json", ...init.headers },
    cache: "no-store",
  });

  if (!response.ok) {
    throw new ApiError(response.status, response.statusText || "Erreur API");
  }
  return (await response.json()) as T;
}
