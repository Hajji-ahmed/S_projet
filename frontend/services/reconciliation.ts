import { apiFetch } from "@/lib/api";
import {
  reconciliationQuery,
  type ReconciliationFilter,
  type TransactionsFilter,
} from "@/lib/reconciliation";
import type {
  Ambigues,
  Candidats,
  Correspondance,
  Correspondances,
  Historique,
  OperationsPage,
  RunResult,
  StatutCorrespondance,
  StatutDecision,
} from "@/types/reconciliation";

const JSON_HEADERS = { "Content-Type": "application/json" };

/** Lance le moteur sur la période : il propose, il ne valide jamais. */
export function runReconciliation(companyId: number, filter: ReconciliationFilter) {
  return apiFetch<RunResult>("/reconciliation/run", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({
      company_id: companyId,
      bank_account_id: filter.bankAccountId ?? null,
      du: filter.from,
      au: filter.to,
    }),
  });
}

export function listTransactions(companyId: number, filter: TransactionsFilter) {
  return apiFetch<OperationsPage>(
    `/reconciliation/transactions${reconciliationQuery(companyId, filter)}`,
  );
}

export function listProposals(
  companyId: number,
  filter: ReconciliationFilter,
  statut: StatutCorrespondance = "Proposée",
) {
  const query = reconciliationQuery(companyId, filter);
  return apiFetch<Correspondances>(
    `/reconciliation/proposals${query}&statut=${encodeURIComponent(statut)}`,
  );
}

export function getMatch(id: number) {
  return apiFetch<Correspondance>(`/reconciliation/matches/${id}`);
}

export function listCandidates(transactionId: number) {
  return apiFetch<Candidats>(`/reconciliation/candidates?transaction_id=${transactionId}`);
}

export function validateMatch(id: number) {
  return apiFetch<Correspondance>(`/reconciliation/matches/${id}/validate`, { method: "POST" });
}

export function validateMatches(ids: number[]) {
  return apiFetch<{ nb_validees: number }>("/reconciliation/matches/validate-batch", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ ids }),
  });
}

export function rejectMatch(id: number, commentaire?: string) {
  return apiFetch<Correspondance>(`/reconciliation/matches/${id}/reject`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ commentaire: commentaire?.trim() || null }),
  });
}

export function cancelMatch(id: number, motif: string) {
  return apiFetch<Correspondance>(`/reconciliation/matches/${id}`, {
    method: "DELETE",
    headers: JSON_HEADERS,
    body: JSON.stringify({ motif }),
  });
}

export function matchManually(transactionId: number, ecritureId: number, commentaire?: string) {
  return apiFetch<Correspondance>("/reconciliation/matches", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({
      transaction_id: transactionId,
      ecriture_id: ecritureId,
      commentaire: commentaire?.trim() || null,
    }),
  });
}

/** Historique des décisions (validées, rejetées, annulées), les plus récentes d'abord. */
export function listHistory(
  companyId: number,
  filter: ReconciliationFilter,
  options: { statut?: StatutDecision; page: number },
) {
  return apiFetch<Historique>(
    `/reconciliation/history${reconciliationQuery(companyId, { ...filter, ...options })}`,
  );
}

/** Opérations ambiguës de la période (à vérifier sans proposition), avec leurs candidates. */
export function listAmbiguous(companyId: number, filter: ReconciliationFilter, page = 1) {
  return apiFetch<Ambigues>(
    `/reconciliation/ambiguous${reconciliationQuery(companyId, { ...filter, page })}`,
  );
}
