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

/**
 * Heure relative d'une action du journal (27/10/2026) : « à l'instant », « il y a 5 min »,
 * « il y a 3 h », « hier », sinon « il y a 4 j ». `maintenant` en millisecondes (tests).
 */
export function heureRelative(iso: string, maintenant: number = Date.now()): string {
  const secondes = Math.max(0, Math.round((maintenant - Date.parse(iso)) / 1000));
  if (secondes < 60) return "à l'instant";
  const minutes = Math.floor(secondes / 60);
  if (minutes < 60) return `il y a ${minutes} min`;
  const heures = Math.floor(minutes / 60);
  if (heures < 24) return `il y a ${heures} h`;
  const jours = Math.floor(heures / 24);
  return jours === 1 ? "hier" : `il y a ${jours} j`;
}

/**
 * Bornes de l'axe des montants d'une courbe (27/10/2026) : du minimum au maximum de la série,
 * avec 10 % de marge, au lieu de partir de 0 (la courbe d'un solde de 70 M paraissait plate).
 */
export function bornesAxe(valeurs: (number | null)[]): [number, number] | null {
  const connues = valeurs.filter((valeur): valeur is number => valeur !== null);
  if (connues.length === 0) return null;
  const mini = Math.min(...connues);
  const maxi = Math.max(...connues);
  const marge = (maxi - mini) * 0.1 || Math.abs(maxi) * 0.05 || 1;
  return [Math.floor(mini - marge), Math.ceil(maxi + marge)];
}
