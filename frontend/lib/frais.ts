import { fromCents, toCents } from "@/lib/statementLines";
import type { PropositionTimbres } from "@/types/frais";

/** Identifiant d'une écriture proposée : sa famille, un compte et un jour. */
export function cleJour(
  item: Pick<PropositionTimbres, "famille" | "bank_account_id" | "date">,
): string {
  return `${item.famille}|${item.bank_account_id}|${item.date}`;
}

/** Nombre de jours cochés et leur total exact (centimes en BigInt, jamais de float). */
export function selectionTimbres(
  propositions: PropositionTimbres[],
  selection: Set<string>,
): { nb: number; total: string } {
  let total = BigInt(0);
  let nb = 0;
  for (const item of propositions) {
    if (!selection.has(cleJour(item))) continue;
    nb += 1;
    total += toCents(item.total);
  }
  return { nb, total: fromCents(total) };
}

/** Libellés proposés pour une écriture saisie à la main (saisie libre). */
export const LIBELLES_SUGGERES = [
  "AGIOS",
  "COM",
  "FRAIS",
  "FRAIS D'ESCOMPTE",
  "FRAIS DE REFINANCEMENT",
  "INTERET CREDOC",
  "INTERETS DEBITEURS",
];

/** Somme exacte (signée) des montants, en texte « -165.00 ». */
export function sommeMontants(montants: string[]): string {
  return fromCents(montants.reduce((total, montant) => total + toCents(montant), BigInt(0)));
}

/**
 * (Frais HT, TVA) d'un total TTC positif, comme le serveur : HT = total ÷ (1 + taux), arrondi au
 * centime le plus proche (0,5 vers le haut) ; TVA = total − HT. Taux en %, « 10 » ou « 7,5 ».
 * Null si le taux n'est pas un nombre positif de 2 décimales au plus.
 */
export function ventilerTva(total: string, taux: string): { ht: string; tva: string } | null {
  const valeur = taux.trim().replace(",", ".");
  if (!/^\d{1,3}(\.\d{1,2})?$/.test(valeur)) return null;
  const centiemes = toCents(valeur); // 10 % → 1000
  if (centiemes <= BigInt(0) || centiemes > BigInt(10000)) return null;
  const ttc = toCents(total);
  const base = BigInt(10000);
  const denominateur = base + centiemes;
  const ht = (BigInt(2) * ttc * base + denominateur) / (BigInt(2) * denominateur);
  return { ht: fromCents(ht), tva: fromCents(ttc - ht) };
}
