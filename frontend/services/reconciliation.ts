import { apiDownload, apiFetch } from "@/lib/api";
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
  EcrituresAmbigues,
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

/** Rejet en lot des propositions choisies, toutes ou aucune (15/10/2026). */
export function rejectMatches(ids: number[], commentaire?: string) {
  return apiFetch<{ nb_traitees: number }>("/reconciliation/matches/reject-batch", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ ids, commentaire: commentaire?.trim() || null }),
  });
}

/** Opérations ambiguës choisies : aucune écriture ne correspond (15/10/2026). */
export function aucuneEcritureLot(ids: number[], commentaire?: string) {
  return apiFetch<{ nb_traitees: number }>("/reconciliation/transactions/aucune-ecriture", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ ids, commentaire: commentaire?.trim() || null }),
  });
}

/** Écritures ambiguës choisies : aucune opération ne correspond (15/10/2026). */
export function aucuneOperationLot(ids: number[], commentaire?: string) {
  return apiFetch<{ nb_traitees: number }>("/reconciliation/entries/aucune-operation", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ ids, commentaire: commentaire?.trim() || null }),
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

export function matchManually(
  transactionId: number,
  ecritureId: number,
  commentaire?: string,
  relanceCiblee = false,
) {
  return apiFetch<Correspondance>("/reconciliation/matches", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({
      transaction_id: transactionId,
      ecriture_id: ecritureId,
      commentaire: commentaire?.trim() || null,
      relance_ciblee: relanceCiblee,
    }),
  });
}

/** Opération ambiguë : aucune écriture candidate ne correspond (15/10/2026). */
export function aucuneEcriture(transactionId: number, commentaire?: string) {
  return apiFetch<{ ecritures_ecartees: number[] }>(
    `/reconciliation/transactions/${transactionId}/aucune-ecriture`,
    {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ commentaire: commentaire?.trim() || null }),
    },
  );
}

/**
 * Rapprochement manuel de plusieurs lignes (1-N, N-1, N-N ; P13 du 15/10/2026). `relanceCiblee`
 * (depuis une carte ambiguë, 16/10/2026) : le moteur ne refait que les lignes en concurrence.
 */
export function matchGroupe(
  transactionIds: number[],
  ecritureIds: number[],
  commentaire?: string,
  relanceCiblee = false,
) {
  return apiFetch<Correspondance>("/reconciliation/matches", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({
      transaction_ids: transactionIds,
      ecriture_ids: ecritureIds,
      commentaire: commentaire?.trim() || null,
      relance_ciblee: relanceCiblee,
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

/** Écritures ambiguës (plusieurs opérations aussi proches), 50 par page (15/10/2026). */
export function listAmbiguousEntries(companyId: number, filter: ReconciliationFilter, page = 1) {
  return apiFetch<EcrituresAmbigues>(
    `/reconciliation/ambiguous-entries${reconciliationQuery(companyId, { ...filter, page })}`,
  );
}

/** Écriture ambiguë : aucune opération candidate ne correspond (15/10/2026). */
export function aucuneOperation(entryId: number, commentaire?: string) {
  return apiFetch<{ operations_ecartees: number[] }>(
    `/reconciliation/entries/${entryId}/aucune-operation`,
    {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ commentaire: commentaire?.trim() || null }),
    },
  );
}

/** Lettrage (rapprochements validés) du filtre de l'historique, en classeur Excel (14/10/2026). */
export function exportLettrage(companyId: number, filter: ReconciliationFilter) {
  return apiDownload(`/reconciliation/export${reconciliationQuery(companyId, filter)}`);
}
