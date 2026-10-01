import { apiFetch } from "@/lib/api";
import type { Bank, BankCreate, BankUpdate } from "@/types/bank";

const JSON_HEADERS = { "Content-Type": "application/json" };

/** Avec `companyId`, le nombre de comptes actifs ne compte que cette société. */
export function listBanks(companyId?: number) {
  return apiFetch<Bank[]>(companyId === undefined ? "/banks" : `/banks?company_id=${companyId}`);
}

export function createBank(data: BankCreate) {
  return apiFetch<Bank>("/banks", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });
}

export function updateBank(id: number, data: BankUpdate) {
  return apiFetch<Bank>(`/banks/${id}`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });
}

export function setBankStatus(id: number, actif: boolean) {
  return apiFetch<Bank>(`/banks/${id}/status`, {
    method: "PATCH",
    headers: JSON_HEADERS,
    body: JSON.stringify({ actif }),
  });
}
