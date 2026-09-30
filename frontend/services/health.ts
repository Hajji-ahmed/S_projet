import { apiFetch } from "@/lib/api";
import type { HealthResponse } from "@/types/health";

export function getHealth() {
  return apiFetch<HealthResponse>("/health");
}
