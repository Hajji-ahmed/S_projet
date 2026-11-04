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

/** État de rapprochement (« Lignes non rapprochées » jusqu'au 04/11/2026) : opérations et
 *  écritures non rapprochées côte à côte par compte, entre les soldes et le contrôle. */
export function exportEtatRapprochement(
  companyId: number,
  from: string,
  to: string,
  bankId?: number,
) {
  const params = new URLSearchParams({ company_id: String(companyId), from, to });
  if (bankId !== undefined) params.set("bank_id", String(bankId));
  return apiDownload(`/rapports/non-rapproches?${params}`);
}

/** Lettrage (rapprochements validés) de la période, d'une banque ou de toutes (04/11/2026). */
export function exportLettrageBanque(companyId: number, from: string, to: string, bankId?: number) {
  const params = new URLSearchParams({ company_id: String(companyId), from, to });
  if (bankId !== undefined) params.set("bank_id", String(bankId));
  return apiDownload(`/reconciliation/export?${params}`);
}
