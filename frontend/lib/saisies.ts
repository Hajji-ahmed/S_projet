/**
 * Tableaux Devises et Prévisions saisis à la main : passage entre la réponse de l'API et le brouillon
 * des cellules (le texte tapé), et validation (mêmes règles que `backend/app/schemas/saisie.py`).
 * Les montants restent en texte : aucun calcul, aucune virgule flottante.
 */
import { amountForInput } from "@/lib/accounts";
import { normalizeSignedAmountInput } from "@/lib/balances";
import type {
  Devises,
  DevisesInput,
  LigneDevise,
  MontantBanque,
  Previsions,
  PrevisionsInput,
} from "@/types/saisie";

export const LIGNES_DEVISES: readonly LigneDevise[] = ["EUR", "USD", "Exp DH convertible"];
/** Colonnes de droite du tableau Devises, après les banques. */
export const COLONNES_DEVISES = [
  { key: "total", label: "TOTAL" },
  { key: "depassement", label: "DEPASSEMENT" },
] as const;

export const NB_LIGNES_PREVISIONS = 14;
export const LIBELLE_MAX = 80;
/** Les trois colonnes fusionnées du tableau Prévisions : un montant pour toute la journée. */
export const COLONNES_JOUR = [
  { key: "encaissement", label: "Encaissement" },
  { key: "escompte", label: "Escompte" },
  { key: "douane", label: "Douane" },
] as const;

/** Texte tapé dans chaque cellule, par clé de cellule. Cellule absente ou vide = vide. */
export type Draft = Record<string, string>;
export type Parsed<T> = { ok: true; value: T } | { ok: false; invalid: string[] };

/** Clé d'une cellule : « EUR|3 » (ligne, banque), « EUR|total », « 5|libelle », « encaissement ». */
export function cellKey(row: string | number, column: string | number): string {
  return `${row}|${column}`;
}

/** Deux brouillons identiques, en ignorant les espaces autour et les cellules vides. */
export function sameDraft(a: Draft, b: Draft): boolean {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  return [...keys].every((key) => (a[key] ?? "").trim() === (b[key] ?? "").trim());
}

function putAmount(draft: Draft, key: string, value: string | null) {
  if (value !== null) draft[key] = amountForInput(value);
}

function putBanks(draft: Draft, row: string | number, cells: MontantBanque[]) {
  for (const cell of cells) putAmount(draft, cellKey(row, cell.bank_id), cell.montant);
}

/** « 1 250,50 » → « 1250.50 » ; vide → null ; invalide → clé ajoutée à `invalid`. */
function amountOf(draft: Draft, key: string, invalid: string[]): string | null {
  // Le signe moins typographique (−) d'un copier-coller vaut un tiret
  const text = (draft[key] ?? "").trim().replace(/^[−‑]/, "-");
  if (!text) return null;
  const value = normalizeSignedAmountInput(text);
  if (value === null) invalid.push(key);
  return value;
}

function banksOf(
  draft: Draft,
  row: string | number,
  bankIds: number[],
  invalid: string[],
): MontantBanque[] {
  return bankIds.flatMap((bankId) => {
    const montant = amountOf(draft, cellKey(row, bankId), invalid);
    return montant === null ? [] : [{ bank_id: bankId, montant }];
  });
}

// --- Devises ---------------------------------------------------------------------------------------

export function devisesToDraft(devises: Devises): Draft {
  const draft: Draft = {};
  for (const line of devises.lignes) {
    putBanks(draft, line.ligne, line.banques);
    putAmount(draft, cellKey(line.ligne, "total"), line.total);
    putAmount(draft, cellKey(line.ligne, "depassement"), line.depassement);
  }
  return draft;
}

/** La grille complète, pour les banques affichées (`bankIds`) : une cellule vide est envoyée vide. */
export function draftToDevisesInput(draft: Draft, bankIds: number[]): Parsed<DevisesInput> {
  const invalid: string[] = [];
  const lignes = LIGNES_DEVISES.map((ligne) => ({
    ligne,
    banques: banksOf(draft, ligne, bankIds, invalid),
    total: amountOf(draft, cellKey(ligne, "total"), invalid),
    depassement: amountOf(draft, cellKey(ligne, "depassement"), invalid),
  }));
  return invalid.length ? { ok: false, invalid } : { ok: true, value: { lignes } };
}

// --- Prévisions ------------------------------------------------------------------------------------

export const LIGNES_PREVISIONS: readonly number[] = Array.from(
  { length: NB_LIGNES_PREVISIONS },
  (_, index) => index + 1,
);

export function previsionsToDraft(previsions: Previsions): Draft {
  const draft: Draft = {};
  for (const line of previsions.lignes) {
    if (line.libelle !== null) draft[cellKey(line.ligne, "libelle")] = line.libelle;
    putBanks(draft, line.ligne, line.banques);
  }
  for (const { key } of COLONNES_JOUR) putAmount(draft, key, previsions[key]);
  return draft;
}

export function draftToPrevisionsInput(draft: Draft, bankIds: number[]): Parsed<PrevisionsInput> {
  const invalid: string[] = [];
  const lignes = LIGNES_PREVISIONS.map((ligne) => {
    const key = cellKey(ligne, "libelle");
    const libelle = (draft[key] ?? "").trim();
    if (libelle.length > LIBELLE_MAX) invalid.push(key);
    return { ligne, libelle: libelle || null, banques: banksOf(draft, ligne, bankIds, invalid) };
  });
  const value: PrevisionsInput = {
    lignes,
    encaissement: amountOf(draft, "encaissement", invalid),
    escompte: amountOf(draft, "escompte", invalid),
    douane: amountOf(draft, "douane", invalid),
  };
  return invalid.length ? { ok: false, invalid } : { ok: true, value };
}
