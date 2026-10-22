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

const INSECABLE = " ";

/**
 * Montant court pour les axes et le centre des graphiques (21/10/2026) : « 18 M », « 1,5 M »,
 * « 250 k », « 2,3 Md ». Espaces insécables : Recharts coupe un libellé d'axe à chaque espace
 * (« 18 000 / 000 »). Affichage uniquement, le montant exact reste dans les infobulles.
 */
export function formatCompact(value: number | string | null | undefined, currency?: string) {
  if (value === null || value === undefined || value === "") return EMPTY_VALUE;
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return EMPTY_VALUE;
  const absolu = Math.abs(n);
  const [diviseur, unite] =
    absolu >= 1e9 ? [1e9, "Md"] : absolu >= 1e6 ? [1e6, "M"] : absolu >= 1e3 ? [1e3, "k"] : [1, ""];
  const reduit = n / diviseur;
  // Une décimale sous 10 (« 1,5 M »), aucune au-delà (« 18 M »)
  const texte = new Intl.NumberFormat("fr-FR", {
    maximumFractionDigits: Math.abs(reduit) < 10 && diviseur > 1 ? 1 : 0,
  })
    .format(reduit)
    .replace(/[\s ]/g, INSECABLE);
  return [texte, unite, currency].filter(Boolean).join(INSECABLE);
}
