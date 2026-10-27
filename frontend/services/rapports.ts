import { apiDownload } from "@/lib/api";

/** Tableau Banques à une date, en Excel (structure imposée). */
export function exportPosition(companyId: number, date: string) {
  const params = new URLSearchParams({ company_id: String(companyId), date });
  return apiDownload(`/rapports/position?${params}`);
}

/** Même tableau Banques en PDF A4 paysage (27/10/2026). */
export function exportPositionPdf(companyId: number, date: string) {
  const params = new URLSearchParams({ company_id: String(companyId), date });
  return apiDownload(`/rapports/position/pdf?${params}`);
}

/** Synthèse par compte et opérations restant à rapprocher sur la période, en Excel. */
export function exportEtatRapprochement(companyId: number, from: string, to: string) {
  const params = new URLSearchParams({ company_id: String(companyId), from, to });
  return apiDownload(`/rapports/rapprochement?${params}`);
}
