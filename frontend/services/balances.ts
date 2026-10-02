import { apiFetch } from "@/lib/api";
import type { Balance, BalanceInput } from "@/types/balance";

/** Historique d'un compte, du plus récent au plus ancien (30 derniers jours par défaut). */
export function listBalances(accountId: number, from?: string, to?: string) {
  const params = new URLSearchParams();
  if (from) params.set("from", from);
  if (to) params.set("to", to);
  const query = params.size ? `?${params}` : "";
  return apiFetch<Balance[]>(`/accounts/${accountId}/balances${query}`);
}

/** Saisit ou corrige la ligne d'un jour (« AAAA-MM-JJ »). */
export function saveBalance(accountId: number, jour: string, data: BalanceInput) {
  return apiFetch<Balance>(`/accounts/${accountId}/balances/${jour}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}
