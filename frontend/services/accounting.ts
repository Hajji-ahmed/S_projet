import { apiFetch } from "@/lib/api";
import {
  accountingForm,
  entriesQuery,
  type AccountingOptions,
  type EntriesFilter,
} from "@/lib/accounting";
import type {
  AnalyseComptable,
  ConfirmationComptable,
  EcritureDetail,
  EcrituresPage,
  ImportComptable,
} from "@/types/accounting";

/** Analyse un export Sage pour une société : rien n'est enregistré. */
export function analyseEntries(file: File, companyId: number, options?: AccountingOptions) {
  return apiFetch<AnalyseComptable>("/accounting/import/analyse", {
    method: "POST",
    body: accountingForm(file, companyId, options),
  });
}

/** Enregistre l'export (le serveur l'analyse à nouveau). */
export function confirmEntries(file: File, companyId: number, options?: AccountingOptions) {
  return apiFetch<ConfirmationComptable>("/accounting/import/confirm", {
    method: "POST",
    body: accountingForm(file, companyId, options),
  });
}

export function listEntries(companyId: number, filter: EntriesFilter) {
  return apiFetch<EcrituresPage>(`/accounting/entries${entriesQuery(companyId, filter)}`);
}

export function getEntry(id: number) {
  return apiFetch<EcritureDetail>(`/accounting/entries/${id}`);
}

export function listAccountingImports(companyId: number) {
  return apiFetch<ImportComptable[]>(`/accounting/imports?company_id=${companyId}`);
}

/** Supprime toutes les écritures d'un export Sage importé (23/10/2026), avec un motif. */
export function supprimerImportComptable(importId: number, motif: string) {
  return apiFetch<{ nb_lignes: number; nb_propositions_retirees: number }>(
    `/accounting/imports/${importId}/supprimer`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ motif }),
    },
  );
}
