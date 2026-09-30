const EMPTY_VALUE = "-";

type FormatAmountOptions = {
  /** Affiche « - » pour un montant égal à zéro (colonnes Débit / Crédit). Sinon « 0 ». */
  dashForZero?: boolean;
};

/**
 * Formate un montant pour l'affichage : « 2 450 000 DH ».
 * Séparateur de milliers = espace, décimales seulement s'il y a des centimes.
 * Valeur absente (null, undefined, vide, non numérique) = « - ».
 *
 * Affichage uniquement : les montants restent calculés côté API (Decimal).
 */
export function formatAmount(
  value: number | string | null | undefined,
  currency?: string,
  { dashForZero = false }: FormatAmountOptions = {},
) {
  if (value === null || value === undefined || value === "") return EMPTY_VALUE;

  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return EMPTY_VALUE;
  if (n === 0 && dashForZero) return EMPTY_VALUE;

  const hasCents = Math.round(n * 100) % 100 !== 0;
  const formatted = new Intl.NumberFormat("fr-FR", {
    minimumFractionDigits: hasCents ? 2 : 0,
    maximumFractionDigits: 2,
  })
    .format(n)
    .replace(/ | /g, " ");

  return currency ? `${formatted} ${currency}` : formatted;
}
