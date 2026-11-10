/**
 * Étape Validation des imports (relevés et Sage) : filtre du tableau piloté par les tuiles
 * « Lignes à importer · Lignes en erreur · Doublons · Lignes ignorées ». Fonctions pures.
 */

import { fromCents, toCents } from "@/lib/statementLines";

export type VueLignes = "toutes" | "importer" | "erreurs" | "doublons" | "ignorees" | "absentes";

/** Clic sur une tuile : elle devient le filtre, ou le retire si elle l'était déjà. */
export function toggleVue(current: VueLignes, clicked: VueLignes): VueLignes {
  return current === clicked ? "toutes" : clicked;
}

type LigneCochable = {
  numero: number;
  statut: string;
  doublon_de: number | null;
  en_cours?: boolean;
  /** Copie d'un frais SIMTIS répétée dans le grand livre (10/11/2026). */
  piece_repetee?: boolean;
};

/** Une ligne déjà importée (doublon sans ligne d'origine dans le fichier) ne se coche jamais. */
export function cochable(line: LigneCochable): boolean {
  return !(line.statut === "Doublon" && line.doublon_de === null);
}

/**
 * Cases cochées par défaut (08/10/2026) : toutes les lignes cochables, valides, en erreur et
 * doublons internes au fichier. Une ligne en erreur cochée bloque la confirmation tant qu'elle
 * n'est pas corrigée (relevés) ou décochée. Sert aussi au bouton « Tout cocher ».
 * `sansEnCours` (07/11/2026) : les opérations en cours « (*) » du relevé restent décochées.
 * Une copie d'un frais SIMTIS répétée dans le grand livre (`piece_repetee`, 10/11/2026) reste
 * décochée : elle se coche à la main si ce sont vraiment deux frais.
 */
export function defaultChecked(
  lines: readonly LigneCochable[],
  options: { sansEnCours?: boolean } = {},
): Set<number> {
  return new Set(
    lines
      .filter(
        (line) => cochable(line) && !line.piece_repetee && !(options.sansEnCours && line.en_cours),
      )
      .map((line) => line.numero),
  );
}

/**
 * Message d'attention quand des frais exportés par SIMTIS reviennent plusieurs fois à l'identique
 * dans le grand livre (10/11/2026) : Sage ne détecte pas les doublons, le tableau des frais y a
 * sans doute été importé deux fois. Null sans pièce répétée.
 */
export function messagePiecesRepetees(
  pieces: readonly { numero_piece: string; bank_code: string | null; nb: number }[],
): string | null {
  if (pieces.length === 0) return null;
  const liste = pieces
    .map(
      (piece) =>
        `${piece.numero_piece}${piece.bank_code ? ` (${piece.bank_code})` : ""}, ${piece.nb} fois`,
    )
    .join(" ; ");
  const un = pieces.length === 1;
  return (
    `Attention : ${pieces.length} N° pièce${un ? "" : "s"} de frais SIMTIS ${un ? "est répété" : "sont répétés"} ` +
    `à l'identique dans ce grand livre (${liste}). Le tableau des frais a peut-être été importé ` +
    "deux fois dans Sage : supprimez la copie dans Sage. Les copies sont décochées ; recochez-les " +
    "seulement s'il s'agit vraiment de frais distincts."
  );
}

/** Lignes cochables marquées « (*) » (opérations en cours), pour la case « Ne pas importer les
 *  opérations en cours » de l'import d'un relevé (07/11/2026). */
export function numerosEnCours(lines: readonly LigneCochable[]): number[] {
  return lines.filter((line) => cochable(line) && line.en_cours).map((line) => line.numero);
}

/** Lignes d'un export Sage à montrer selon la tuile choisie (« importer » : lignes cochées ;
 *  « erreurs » : lignes en erreur encore cochées, comme pour les relevés). */
export function sageLinesFor<T extends { numero: number; statut: string }>(
  lines: readonly T[],
  vue: VueLignes,
  cochees: ReadonlySet<number>,
): T[] {
  switch (vue) {
    case "importer":
      return lines.filter((line) => cochees.has(line.numero));
    case "erreurs":
      return lines.filter((line) => line.statut === "Erreur" && cochees.has(line.numero));
    case "doublons":
      return lines.filter((line) => line.statut === "Doublon");
    case "ignorees":
    case "absentes":
      return [];
    default:
      return [...lines];
  }
}

/** Contenu d'une ligne ignorée sur une seule ligne : cellules non vides séparées par « · ». */
export function cellulesText(cellules: readonly string[]): string {
  return cellules.filter((cell) => cell.trim() !== "").join(" · ") || "(ligne vide)";
}

/** Lignes par page de l'aperçu d'un import (08/10/2026 : fichiers jusqu'à 50 000 lignes). */
export const LIGNES_PAR_PAGE = 100;

/** Une page de lignes (numérotée à partir de 1), ramenée dans les bornes, et le nombre de pages. */
export function pageOf<T>(
  rows: readonly T[],
  page: number,
  size: number = LIGNES_PAR_PAGE,
): { rows: T[]; page: number; pages: number } {
  const pages = Math.max(1, Math.ceil(rows.length / size));
  const current = Math.min(Math.max(1, page), pages);
  return { rows: rows.slice((current - 1) * size, current * size), page: current, pages };
}

export type BlocageImport = {
  raison: "deja_importe" | "aucune" | "erreurs" | "ouverture";
  message: string;
};

/**
 * Pourquoi « Confirmer l'import » est désactivé (08/10/2026) : la première raison qui s'applique,
 * affichée à côté du bouton ; null quand rien ne bloque. `ouvertureManquante` : relevé sans soldes
 * dont le solde d'ouverture n'est pas saisi (toujours faux pour Sage).
 */
export function blocageImport(etat: {
  dejaImporte: boolean;
  cochees: number;
  erreursCochees: number;
  ouvertureManquante?: boolean;
  correction?: "relevé" | "Sage";
  /** Écritures absentes du grand livre cochées « Supprimer » (Sage, 05/11/2026). */
  suppressions?: number;
}): BlocageImport | null {
  if (etat.dejaImporte) {
    return { raison: "deja_importe", message: "Ce fichier a déjà été importé." };
  }
  if (etat.cochees === 0 && !etat.suppressions) {
    return { raison: "aucune", message: "Cochez au moins une ligne à importer." };
  }
  if (etat.erreursCochees > 0) {
    const n = etat.erreursCochees;
    const s = n > 1 ? "s" : "";
    const la = n > 1 ? "les" : "la";
    const corriger = etat.correction === "Sage" ? "corrigez l'export dans Sage" : `corrigez-${la}`;
    return {
      raison: "erreurs",
      message: `${n} ligne${s} cochée${s} en erreur : ${corriger} ou décochez-${la}.`,
    };
  }
  if (etat.ouvertureManquante) {
    return {
      raison: "ouverture",
      message: "Saisissez le solde d'ouverture : ce fichier n'a pas de soldes.",
    };
  }
  return null;
}

export type TotauxCoches = { debit: string; credit: string; solde: string };

/**
 * Totaux des lignes cochées d'un export Sage (29/10/2026) : débit, crédit et solde = débit − crédit,
 * comme le grand livre du compte banque. Sommés en centimes exacts ; un montant vide compte 0.
 */
export function totauxCoches(
  lines: readonly { numero: number; debit: string | null; credit: string | null }[],
  cochees: ReadonlySet<number>,
): TotauxCoches {
  let debit = BigInt(0);
  let credit = BigInt(0);
  for (const line of lines) {
    if (!cochees.has(line.numero)) continue;
    if (line.debit) debit += toCents(line.debit);
    if (line.credit) credit += toCents(line.credit);
  }
  return { debit: fromCents(debit), credit: fromCents(credit), solde: fromCents(debit - credit) };
}

type Absente = {
  id: number;
  bank_account_id: number;
  date_ecriture: string;
  debit: string;
  credit: string;
  code_rapprochement: string | null;
  a_verifier: boolean;
};

/** Une écriture absente rapprochée ne se supprime pas : son rapprochement s'annule d'abord. */
export function supprimable(absente: Pick<Absente, "code_rapprochement">): boolean {
  return absente.code_rapprochement === null;
}

/**
 * Écritures absentes du grand livre cochées « Supprimer » par défaut (05/11/2026) : toutes celles
 * qui se suppriment, sauf sur un compte dont le fichier a des lignes en erreur (`a_verifier`).
 */
export function absentesParDefaut(absentes: readonly Absente[]): Set<number> {
  return new Set(
    absentes.filter((item) => supprimable(item) && !item.a_verifier).map((item) => item.id),
  );
}

export type SoldeApresImport = {
  bank_account_id: number;
  bank_code: string;
  journal: string;
  date: string | null;
  /** Null : solde d'ouverture à saisir (`raison` « ouverture ») ou daté après le fichier (« apres ») */
  solde: string | null;
  raison: "ouverture" | "apres" | null;
};

/**
 * Solde comptable de chaque compte après l'import (03/11/2026) : son solde avant import à la
 * dernière date du fichier + débit − crédit de ses lignes cochées datées après son solde
 * d'ouverture (règle de la carte « Solde comptable »). Centimes exacts ; jamais un départ à 0.
 */
export function soldesApresImport(
  comptes: readonly {
    bank_account_id: number;
    bank_code: string;
    journal: string;
    date_solde?: string | null;
    date_ouverture?: string | null;
    solde_avant?: string | null;
  }[],
  lines: readonly {
    numero: number;
    bank_account_id: number | null;
    date_ecriture: string | null;
    debit: string | null;
    credit: string | null;
  }[],
  cochees: ReadonlySet<number>,
  absentes: readonly Absente[] = [],
  supprimees: ReadonlySet<number> = new Set(),
): SoldeApresImport[] {
  return comptes.map((compte) => {
    const base = {
      bank_account_id: compte.bank_account_id,
      bank_code: compte.bank_code,
      journal: compte.journal,
      date: compte.date_solde ?? null,
    };
    if (compte.solde_avant == null) {
      return { ...base, solde: null, raison: compte.date_ouverture ? "apres" : "ouverture" };
    }
    let solde = toCents(compte.solde_avant);
    for (const line of lines) {
      if (!cochees.has(line.numero) || line.bank_account_id !== compte.bank_account_id) continue;
      // Dates ISO (AAAA-MM-JJ) : l'ordre des textes est celui des jours
      if (
        !line.date_ecriture ||
        (compte.date_ouverture && line.date_ecriture <= compte.date_ouverture)
      )
        continue;
      if (line.debit) solde += toCents(line.debit);
      if (line.credit) solde -= toCents(line.credit);
    }
    // Écritures absentes du fichier cochées « Supprimer » (05/11/2026) : comptées dans le solde
    // avant import, elles en sortent
    for (const item of absentes) {
      if (!supprimees.has(item.id) || item.bank_account_id !== compte.bank_account_id) continue;
      if (compte.date_ouverture && item.date_ecriture <= compte.date_ouverture) continue;
      solde -= toCents(item.debit) - toCents(item.credit);
    }
    return { ...base, solde: fromCents(solde), raison: null };
  });
}

/** Ce que fera « Confirmer l'import » d'un export Sage : écritures enregistrées et supprimées. */
export function messageConfirmation(importees: number, supprimees: number): string {
  const s = (n: number) => (n > 1 ? "s" : "");
  const ajout = `${importees} écriture${s(importees)} ser${importees > 1 ? "ont" : "a"} enregistrée${s(importees)}`;
  if (supprimees === 0) return `${ajout}.`;
  return `${ajout}, ${supprimees} supprimée${s(supprimees)} (absente${s(supprimees)} du grand livre).`;
}

/** Coche ou décoche d'un clic un groupe de lignes (les erreurs), sans toucher aux autres. Depuis
 * le 12/10/2026, un doublon est une ligne déjà en base, jamais cochable : pas de groupe Doublons. */
export function basculerGroupe(
  cochees: ReadonlySet<number>,
  groupe: readonly number[],
  cocher: boolean,
): Set<number> {
  const next = new Set(cochees);
  for (const numero of groupe) {
    if (cocher) next.add(numero);
    else next.delete(numero);
  }
  return next;
}
