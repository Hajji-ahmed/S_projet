/**
 * Saisie manuelle d'une opération ou d'une écriture (24/10/2026) : règles pures de l'écran. Les
 * montants restent en TEXTE exact ; l'API refait toutes les vérifications.
 */
import { normalizeAmountInput } from "@/lib/accounts";

export type Sens = "debit" | "credit";

/** « 1 250,50 » au débit → { debit: "1250.50", credit: null } ; null si le montant est illisible
 * ou nul. */
export function montantsSaisis(
  sens: Sens,
  texte: string,
): { debit: string | null; credit: string | null } | null {
  const montant = normalizeAmountInput(texte);
  if (montant === null || /^0+(\.0+)?$/.test(montant)) return null;
  return sens === "debit" ? { debit: montant, credit: null } : { debit: null, credit: montant };
}

/** Journaux Sage d'un compte : « 5243,5543 » → [« 5243 », « 5543 »]. */
export function journauxDuCompte(journal: string | null | undefined): string[] {
  return (journal ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}
