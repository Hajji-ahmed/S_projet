import { apiFetch } from "@/lib/api";
import {
  accountingForm,
  entriesQuery,
  type AccountingOptions,
  type ChampsCorriges,
  type EntriesFilter,
} from "@/lib/accounting";
import type {
  AnalyseComptable,
  ConfirmationComptable,
  EcritureDetail,
  EcrituresPage,
  ImportComptable,
  SageAnalyse,
  SageComparaison,
  SageEcartDetail,
  SageEtat,
  SageSoldes,
  SoldeComptable,
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

/** Écriture saisie à la main (24/10/2026). */
export type EcritureManuelle = {
  bank_account_id: number;
  journal: string;
  date_ecriture: string;
  libelle: string;
  numero_piece: string | null;
  reference: string | null;
  echeance: string | null;
  debit: string | null;
  credit: string | null;
  montant_devise: string | null;
  /** Compte comptable choisi parmi ceux du compte bancaire (27/10/2026). */
  compte: string | null;
  motif: string;
};

export function ajouterEcriture(ecriture: EcritureManuelle) {
  return apiFetch<EcritureDetail>("/accounting/entries", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(ecriture),
  });
}

/** Corrige une écriture du grand livre avec un motif (19/11/2026) : seuls les champs envoyés
 * changent. */
export function modifierEcriture(entryId: number, champs: ChampsCorriges, motif: string) {
  return apiFetch<EcritureDetail>(`/accounting/entries/${entryId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...champs, motif }),
  });
}

/** Supprime une écriture (importée ou manuelle) non rapprochée, avec un motif. */
export function supprimerEcriture(entryId: number, motif: string) {
  return apiFetch<void>(`/accounting/entries/${entryId}/supprimer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ motif }),
  });
}

/** Solde comptable de chaque compte à une date (26/10/2026). */
export function listSoldesComptables(companyId: number, jour: string) {
  return apiFetch<SoldeComptable[]>(`/accounting/soldes?company_id=${companyId}&date=${jour}`);
}

/** Saisit (ou efface, tout à null) le solde comptable d'ouverture d'un compte. */
export function setSoldeOuverture(
  accountId: number,
  body: { date_ouverture: string | null; solde: string | null; solde_devise: string | null },
) {
  return apiFetch<SoldeComptable | null>(`/accounting/soldes/${accountId}/ouverture`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** Base Sage reliée à la société, date de sa dernière copie, comptes lus (21/11/2026). */
export function sageEtat(companyId: number) {
  return apiFetch<SageEtat>(`/accounting/sage/etat?company_id=${companyId}`);
}

/** Lit le grand livre de chaque compte courant MAD dans la base Sage : rien n'est enregistré. */
export function sageAnalyse(companyId: number, du: string, au: string) {
  return apiFetch<SageAnalyse>("/accounting/sage/analyse", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ company_id: companyId, du, au }),
  });
}

/** Importe les lignes cochées d'un compte (la base Sage est relue et doit être inchangée). */
export function sageConfirm(request: {
  companyId: number;
  bankAccountId: number;
  du: string;
  au: string;
  empreinte: string;
  lignesChoisies: number[];
  ecrituresSupprimees: number[];
}) {
  return apiFetch<ConfirmationComptable>("/accounting/sage/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      company_id: request.companyId,
      bank_account_id: request.bankAccountId,
      du: request.du,
      au: request.au,
      empreinte: request.empreinte,
      lignes_choisies: request.lignesChoisies,
      ecritures_supprimees: request.ecrituresSupprimees,
    }),
  });
}

/** Solde Sage, solde comptable SIMTIS et écart de chaque compte courant MAD (21/11/2026). */
export function sageSoldes(companyId: number, jour: string) {
  return apiFetch<SageSoldes>(`/accounting/sage/soldes?company_id=${companyId}&date=${jour}`);
}

/** D'où vient l'écart d'un compte : départ, journaux, non exportées, lignes hors journaux. */
export function sageEcart(bankAccountId: number, jour: string) {
  return apiFetch<SageEcartDetail>(
    `/accounting/sage/ecart?bank_account_id=${bankAccountId}&date=${jour}`,
  );
}

/** Écritures des journaux de banque présentes d'un seul côté, Sage ou SIMTIS. */
export function sageComparaison(bankAccountId: number, jour: string) {
  return apiFetch<SageComparaison>(
    `/accounting/sage/comparaison?bank_account_id=${bankAccountId}&date=${jour}`,
  );
}
