/**
 * Écart entre le solde d'un compte dans Sage et son solde comptable SIMTIS (21/11/2026).
 * Montants en texte exact, calculs en centimes. Fonctions pures.
 */

import { fromCents, toCents } from "@/lib/statementLines";

export type EtatEcart = "aucun" | "ecart" | "inconnu";

/** Aucun écart (0,00), un écart, ou rien à comparer (solde SIMTIS sans ouverture). */
export function etatEcart(ecart: string | null | undefined): EtatEcart {
  if (ecart === null || ecart === undefined) return "inconnu";
  return toCents(ecart) === BigInt(0) ? "aucun" : "ecart";
}

/**
 * Écart Sage − SIMTIS une fois les lignes cochées importées (panneau « Récupérer le GL ») : null
 * s'il manque l'un des deux soldes.
 */
export function ecartApresImport(
  soldeSage: string | null | undefined,
  soldeApresImport: string | null | undefined,
): string | null {
  if (soldeSage == null || soldeApresImport == null) return null;
  return difference(soldeSage, soldeApresImport);
}

/** a − b au centime : « 1150.00 » − « 1180.00 » → « -30.00 ». */
export function difference(a: string, b: string): string {
  return fromCents(toCents(a) - toCents(b));
}

/** Veille d'une date « AAAA-MM-JJ » (calcul en UTC : aucun décalage de fuseau). */
export function veille(iso: string | null): string | null {
  if (!iso) return null;
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day - 1)).toISOString().slice(0, 10);
}

/** Phrase qui dit dans quel sens va l'écart, pour l'aide sous le montant. */
export function sensEcart(ecart: string | null | undefined): string | null {
  if (etatEcart(ecart) !== "ecart") return null;
  return toCents(ecart as string) > BigInt(0)
    ? "Sage plus débiteur que SIMTIS"
    : "Sage plus créditeur que SIMTIS";
}
