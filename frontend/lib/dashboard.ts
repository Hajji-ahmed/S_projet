/** Dashboard (P15) : règles d'affichage pures. Aucun calcul métier : tout vient de l'API. */
import { toCents } from "@/lib/statementLines";

/** Période proposée : du 1er du mois à aujourd'hui (« AAAA-MM-JJ »). */
export function moisEnCours(today: string): { from: string; to: string } {
  return { from: `${today.slice(0, 8)}01`, to: today };
}

/** « 2.5 » → « +2,5 % » ; « -10.0 » → « -10,0 % » ; null → null. */
export function formatVariation(variation: string | null): string | null {
  if (variation === null) return null;
  const signe = variation.startsWith("-") ? "" : "+";
  return `${signe}${variation.replace(".", ",")} %`;
}

/** Sens de la variation pour la flèche et la couleur. */
export function tendance(variation: string | null): "up" | "down" {
  return variation?.startsWith("-") ? "down" : "up";
}

/** Part entière en % (0 à 100) ; 0 quand le total est nul. */
export function pourcentage(partie: number, total: number): number {
  return total > 0 ? Math.round((partie * 100) / total) : 0;
}

/** Part d'une catégorie de frais dans le total, en % avec une décimale (« 27,9 »). */
export function partFrais(montant: string, total: string): string {
  const t = toCents(total);
  if (t === BigInt(0)) return "0,0";
  const pourMille = (toCents(montant) * BigInt(1000) + t / BigInt(2)) / t;
  return `${pourMille / BigInt(10)},${pourMille % BigInt(10)}`;
}

const MOIS = [
  "janv.",
  "févr.",
  "mars",
  "avr.",
  "mai",
  "juin",
  "juil.",
  "août",
  "sept.",
  "oct.",
  "nov.",
  "déc.",
];

/** « 2026-10-01 » → « 1 oct. » (axe des graphiques). */
export function jourCourt(iso: string): string {
  return `${Number(iso.slice(8, 10))} ${MOIS[Number(iso.slice(5, 7)) - 1]}`;
}

/** « 2026-10-01 », « 2026-10-14 » → « 1 oct. 2026 - 14 oct. 2026 ». */
export function libellePeriode(from: string, to: string): string {
  if (!from || !to) return "Choisir une période";
  return `${jourCourt(from)} ${from.slice(0, 4)} - ${jourCourt(to)} ${to.slice(0, 4)}`;
}
