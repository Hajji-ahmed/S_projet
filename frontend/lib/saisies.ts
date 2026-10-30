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

export const LIBELLE_MAX = 80;
/** Les trois colonnes sans banque du tableau Prévisions : un montant par ligne (03/10/2026). */
export const COLONNES_JOUR = [
  { key: "encaissement", label: "Encaissement" },
  { key: "escompte", label: "Escompte" },
  { key: "douane", label: "Douane" },
] as const;

/** Texte tapé dans chaque cellule, par clé de cellule. Cellule absente ou vide = vide. */
export type Draft = Record<string, string>;
export type Parsed<T> = { ok: true; value: T } | { ok: false; invalid: string[] };

/** Clé d'une cellule : « EUR|3 » (ligne, banque), « EUR|total », « 5|libelle », « 5|encaissement ». */
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

/** Au plus 99 lignes par date (`LIGNES_PREVISIONS_PAR_DATE` du backend). */
export const LIGNES_PAR_DATE_MAX = 99;

/**
 * Une ligne du tableau Prévisions dans le brouillon : `id` est propre à l'écran (les lignes chargées
 * puis les lignes ajoutées), `jour` sa date (décision du 30/10/2026). Ses cellules sont « id|… ».
 */
export type LigneBrouillon = { id: number; jour: string };

/** Les lignes du brouillon, par date puis dans l'ordre d'ajout (l'ordre envoyé au serveur). */
export function lignesPrevisions(draft: Draft): LigneBrouillon[] {
  const lignes: LigneBrouillon[] = [];
  for (const [key, value] of Object.entries(draft)) {
    const [row, column] = key.split("|");
    if (column === "jour") lignes.push({ id: Number(row), jour: value });
  }
  return lignes.sort((a, b) => a.jour.localeCompare(b.jour) || a.id - b.id);
}

/** Lignes regroupées par date, pour la cellule de date fusionnée de chaque groupe. */
export function groupesParDate(
  lignes: LigneBrouillon[],
): { jour: string; lignes: LigneBrouillon[] }[] {
  const groupes: { jour: string; lignes: LigneBrouillon[] }[] = [];
  for (const ligne of lignes) {
    const dernier = groupes.at(-1);
    if (dernier?.jour === ligne.jour) dernier.lignes.push(ligne);
    else groupes.push({ jour: ligne.jour, lignes: [ligne] });
  }
  return groupes;
}

/** Ajoute une ligne vide à la date `jour`, après les lignes de cette date. */
export function ajouterLigne(draft: Draft, jour: string): Draft {
  const id = Math.max(0, ...lignesPrevisions(draft).map((ligne) => ligne.id)) + 1;
  return { ...draft, [cellKey(id, "jour")]: jour };
}

/** Retire la ligne `id` et toutes ses cellules. */
export function supprimerLigne(draft: Draft, id: number): Draft {
  return Object.fromEntries(Object.entries(draft).filter(([key]) => !key.startsWith(`${id}|`)));
}

export function previsionsToDraft(previsions: Previsions): Draft {
  const draft: Draft = {};
  previsions.lignes.forEach((line, index) => {
    const id = index + 1;
    draft[cellKey(id, "jour")] = line.jour;
    if (line.libelle !== null) draft[cellKey(id, "libelle")] = line.libelle;
    putBanks(draft, id, line.banques);
    for (const { key } of COLONNES_JOUR) putAmount(draft, cellKey(id, key), line[key]);
  });
  return draft;
}

/** Toutes les lignes affichées, dans l'ordre : une ligne absente est supprimée par le serveur. */
export function draftToPrevisionsInput(draft: Draft, bankIds: number[]): Parsed<PrevisionsInput> {
  const invalid: string[] = [];
  const lignes = lignesPrevisions(draft).map(({ id, jour }) => {
    const key = cellKey(id, "libelle");
    const libelle = (draft[key] ?? "").trim();
    if (libelle.length > LIBELLE_MAX) invalid.push(key);
    return {
      jour,
      libelle: libelle || null,
      banques: banksOf(draft, id, bankIds, invalid),
      encaissement: amountOf(draft, cellKey(id, "encaissement"), invalid),
      escompte: amountOf(draft, cellKey(id, "escompte"), invalid),
      douane: amountOf(draft, cellKey(id, "douane"), invalid),
    };
  });
  return invalid.length ? { ok: false, invalid } : { ok: true, value: { lignes } };
}
