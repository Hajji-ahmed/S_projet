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
