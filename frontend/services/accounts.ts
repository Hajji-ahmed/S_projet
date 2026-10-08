import { apiFetch } from "@/lib/api";
import type { Account, AccountCreate, AccountFilters, AccountUpdate } from "@/types/account";

const JSON_HEADERS = { "Content-Type": "application/json" };

/** Comptes d'UNE société : l'API refuse une liste sans société. */
export function listAccounts(companyId: number, filters: AccountFilters = {}) {
  const params = new URLSearchParams({ company_id: String(companyId) });
  if (filters.bank_id !== undefined) params.set("bank_id", String(filters.bank_id));
  if (filters.devise) params.set("devise", filters.devise);
  if (filters.actif !== undefined) params.set("actif", String(filters.actif));
  return apiFetch<Account[]>(`/accounts?${params}`);
}

export function createAccount(data: AccountCreate) {
  return apiFetch<Account>("/accounts", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });
}

export function updateAccount(id: number, data: AccountUpdate) {
  return apiFetch<Account>(`/accounts/${id}`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });
}

export function setAccountStatus(id: number, actif: boolean) {
  return apiFetch<Account>(`/accounts/${id}/status`, {
    method: "PATCH",
    headers: JSON_HEADERS,
    body: JSON.stringify({ actif }),
  });
}

/** Supprime un compte sans historique (et ses soldes saisis) ; 409 s'il a un historique. */
export function deleteAccount(id: number) {
  return apiFetch<void>(`/accounts/${id}`, { method: "DELETE" });
}
