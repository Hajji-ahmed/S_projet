/**
 * Étape Validation des imports (relevés et Sage) : filtre du tableau piloté par les tuiles
 * « Lignes à importer · Lignes en erreur · Doublons · Lignes ignorées ». Fonctions pures.
 */

export type VueLignes = "toutes" | "importer" | "erreurs" | "doublons" | "ignorees";

/** Clic sur une tuile : elle devient le filtre, ou le retire si elle l'était déjà. */
export function toggleVue(current: VueLignes, clicked: VueLignes): VueLignes {
  return current === clicked ? "toutes" : clicked;
}

/** Lignes d'un export Sage à montrer selon la tuile choisie (« importer » : lignes valides et
 *  doublons internes gardés). */
export function sageLinesFor<T extends { numero: number; statut: string }>(
  lines: readonly T[],
  vue: VueLignes,
  gardees: ReadonlySet<number>,
): T[] {
  switch (vue) {
    case "importer":
      return lines.filter(
        (line) =>
          line.statut === "Valide" || (line.statut === "Doublon" && gardees.has(line.numero)),
      );
    case "erreurs":
      return lines.filter((line) => line.statut === "Erreur");
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
