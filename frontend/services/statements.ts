import { apiDownload, apiFetch } from "@/lib/api";
import { importForm, periodQuery, type Period } from "@/lib/statements";
import type {
  AccountStatement,
  Analysis,
  Confirmation,
  ConfirmOptions,
  ImportRequest,
  Statement,
  Transaction,
  TransactionUpdate,
} from "@/types/statement";

/** Analyse un relevé et renvoie son aperçu. Rien n'est enregistré. */
export function analyseStatement(request: ImportRequest) {
  // Pas d'en-tête Content-Type : le navigateur ajoute celui du multipart, avec sa frontière
  return apiFetch<Analysis>("/statements/import/analyse", {
    method: "POST",
    body: importForm(request),
  });
}

/** Enregistre le relevé : même fichier et même correspondance que l'aperçu validé. */
export function confirmStatement(request: ImportRequest, options: ConfirmOptions) {
  return apiFetch<Confirmation>("/statements/import/confirm", {
    method: "POST",
    body: importForm(request, options),
  });
}

/** Journal des imports d'UNE société, du plus récent au plus ancien. */
export function listStatements(companyId: number) {
  return apiFetch<Statement[]>(
    `/statements?${new URLSearchParams({ company_id: String(companyId) })}`,
  );
}

/** Relevé continu d'un compte : tous ses imports à la suite, sur une période facultative. */
export function getAccountStatement(accountId: number, period: Period = {}) {
  return apiFetch<AccountStatement>(`/statements/accounts/${accountId}${periodQuery(period)}`);
}

/** Modifie Pointage, Lettrage / Escompte et Commentaire d'une opération importée. */
export function updateTransaction(transactionId: number, data: TransactionUpdate) {
  return apiFetch<Transaction>(`/statements/transactions/${transactionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

/** Relevé continu du compte au format standard (11 colonnes), en classeur Excel. */
export function exportAccountStatement(accountId: number, period: Period = {}) {
  return apiDownload(`/statements/accounts/${accountId}/export${periodQuery(period)}`);
}

/** Supprime des opérations en cours (toutes ou aucune), avant le relevé suivant (21/10/2026). */
export function supprimerEnCours(ids: number[]) {
  return apiFetch<{ nb: number }>("/statements/transactions/supprimer-en-cours", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids }),
  });
}

/** Supprime tout ce qu'un relevé importé a apporté (23/10/2026), avec un motif. */
export function supprimerReleve(statementId: number, motif: string) {
  return apiFetch<{ nb_lignes: number; nb_propositions_retirees: number }>(
    `/statements/${statementId}/supprimer`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ motif }),
    },
  );
}

/** Opération saisie à la main (24/10/2026). */
export type OperationManuelle = {
  date_operation: string;
  date_valeur: string | null;
  libelle: string;
  reference: string | null;
  debit: string | null;
  credit: string | null;
  pointage_type_id: number | null;
  commentaire: string | null;
  motif: string;
};

export function ajouterOperation(accountId: number, operation: OperationManuelle) {
  return apiFetch<Transaction>(`/statements/accounts/${accountId}/operations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(operation),
  });
}

/** Supprime une opération (importée ou manuelle) non rapprochée, avec un motif. */
export function supprimerOperation(transactionId: number, motif: string) {
  return apiFetch<void>(`/statements/transactions/${transactionId}/supprimer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ motif }),
  });
}
