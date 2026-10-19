import { apiFetch } from "@/lib/api";
import type { Alerte, Dashboard } from "@/types/dashboard";

/** Vue d'ensemble de la société sur la période (P15, 14/10/2026). */
export function getDashboard(companyId: number, from: string, to: string, bankId?: number) {
  const params = new URLSearchParams({ company_id: String(companyId), from, to });
  if (bankId !== undefined) params.set("bank_id", String(bankId));
  return apiFetch<Dashboard>(`/dashboard?${params}`);
}

/** Alertes du mois en cours : la cloche de l'en-tête. */
export function getAlertes(companyId: number) {
  return apiFetch<{ alertes: Alerte[] }>(`/dashboard/alertes?company_id=${companyId}`);
}
