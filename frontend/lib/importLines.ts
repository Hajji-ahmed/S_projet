/**
 * Étape Validation des imports (relevés et Sage) : filtre du tableau piloté par les tuiles
 * « Lignes à importer · Lignes en erreur · Doublons · Lignes ignorées ». Fonctions pures.
 */

export type VueLignes = "toutes" | "importer" | "erreurs" | "doublons" | "ignorees";

/** Clic sur une tuile : elle devient le filtre, ou le retire si elle l'était déjà. */
export function toggleVue(current: VueLignes, clicked: VueLignes): VueLignes {
  return current === clicked ? "toutes" : clicked;
}

type LigneCochable = { numero: number; statut: string; doublon_de: number | null };

/** Une ligne déjà importée (doublon sans ligne d'origine dans le fichier) ne se coche jamais. */
export function cochable(line: LigneCochable): boolean {
  return !(line.statut === "Doublon" && line.doublon_de === null);
}

/**
 * Cases cochées par défaut (08/10/2026) : toutes les lignes cochables, valides, en erreur et
 * doublons internes au fichier. Une ligne en erreur cochée bloque la confirmation tant qu'elle
 * n'est pas corrigée (relevés) ou décochée. Sert aussi au bouton « Tout cocher ».
 */
export function defaultChecked(lines: readonly LigneCochable[]): Set<number> {
  return new Set(lines.filter(cochable).map((line) => line.numero));
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
}): BlocageImport | null {
  if (etat.dejaImporte) {
    return { raison: "deja_importe", message: "Ce fichier a déjà été importé." };
  }
  if (etat.cochees === 0) {
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
