import { apiFetch } from "@/lib/api";
import { discrepanciesQuery, type DiscrepanciesFilter } from "@/lib/discrepancies";
import type {
  EcartCreate,
  EcartDetail,
  EcartsPage,
  EcartUpdate,
  GenerationEcarts,
  Responsable,
} from "@/types/discrepancy";

const JSON_HEADERS = { "Content-Type": "application/json" };

export function listDiscrepancies(companyId: number, filter: DiscrepanciesFilter) {
  return apiFetch<EcartsPage>(`/discrepancies${discrepanciesQuery(companyId, filter)}`);
}

export function getDiscrepancy(id: number) {
  return apiFetch<EcartDetail>(`/discrepancies/${id}`);
}

export function listResponsables(companyId: number) {
  return apiFetch<Responsable[]>(`/discrepancies/responsables?company_id=${companyId}`);
}

export function createDiscrepancy(data: EcartCreate) {
  return apiFetch<EcartDetail>("/discrepancies", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });
}

/** Crée les écarts de la période : doublons potentiels, lignes restées sans pendant. */
export function generateDiscrepancies(
  companyId: number,
  period: { from: string; to: string; bankAccountId?: number },
) {
  return apiFetch<GenerationEcarts>("/discrepancies/generate", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({
      company_id: companyId,
      bank_account_id: period.bankAccountId ?? null,
      du: period.from,
      au: period.to,
    }),
  });
}

/** Seuls les champs présents changent ; `responsable_id: null` retire le responsable. */
export function updateDiscrepancy(id: number, data: EcartUpdate) {
  return apiFetch<EcartDetail>(`/discrepancies/${id}`, {
    method: "PATCH",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });
}

export function closeDiscrepancy(id: number, commentaire: string) {
  return apiFetch<EcartDetail>(`/discrepancies/${id}/close`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ commentaire }),
  });
}
