const EMPTY_VALUE = "-";

type FormatAmountOptions = {
  /** Affiche « - » pour un montant égal à zéro (colonnes Débit / Crédit). Sinon « 0,00 ». */
  dashForZero?: boolean;
  /** Décimales seulement s'il y a des centimes (« 500 000 ») : champs de saisie (11/11/2026). */
  centimesSiBesoin?: boolean;
};

/**
 * Formate un montant pour l'affichage : « 2 450 000,00 DH ».
 * Séparateur de milliers = espace, toujours 2 décimales (11/11/2026 ; avant, seulement s'il y avait
 * des centimes). Valeur absente (null, undefined, vide, non numérique) = « - ». Pour un compteur
 * (nombre de lignes, de propositions), utiliser `formatNombre`.
 *
 * Affichage uniquement : les montants restent calculés côté API (Decimal).
 */
export function formatAmount(
  value: number | string | null | undefined,
  currency?: string,
  { dashForZero = false, centimesSiBesoin = false }: FormatAmountOptions = {},
) {
  if (value === null || value === undefined || value === "") return EMPTY_VALUE;

  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return EMPTY_VALUE;
  if (n === 0 && dashForZero) return EMPTY_VALUE;

  const hasCents = Math.round(n * 100) % 100 !== 0;
  const formatted = new Intl.NumberFormat("fr-FR", {
    minimumFractionDigits: hasCents || !centimesSiBesoin ? 2 : 0,
    maximumFractionDigits: 2,
  })
    .format(n)
    .replace(/ | /g, " ");

  return currency ? `${formatted} ${currency}` : formatted;
}

const INSECABLE = " ";

/** Compteur (lignes, propositions, frais) : « 6 469 », sans décimales (11/11/2026). */
export function formatNombre(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return EMPTY_VALUE;
  return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 })
    .format(value)
    .replace(/[  ]/g, " ");
}

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
