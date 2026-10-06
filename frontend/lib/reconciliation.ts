/** Rapprochement 1→1 (P11) : règles pures de l'écran. Montants en texte exact, jamais en float. */
import { fromCents, toCents } from "@/lib/statementLines";
import type { Correspondance } from "@/types/reconciliation";

export type ReconciliationFilter = {
  bankAccountId?: number;
  from: string;
  to: string;
};

export type TransactionsFilter = ReconciliationFilter & {
  statut?: string;
  q?: string;
  page: number;
};

/** Période proposée à l'ouverture : du 1er du mois précédent à aujourd'hui (« AAAA-MM-JJ »). */
export function defaultPeriod(today: string): { from: string; to: string } {
  const [year, month] = today.split("-").map(Number);
  const previous = month === 1 ? { y: year - 1, m: 12 } : { y: year, m: month - 1 };
  return { from: `${previous.y}-${String(previous.m).padStart(2, "0")}-01`, to: today };
}

/** « ?company_id=…&… » : seuls les filtres renseignés ; `page` seulement si demandée. */
export function reconciliationQuery(
  companyId: number,
  filter: Partial<TransactionsFilter>,
): string {
  const params = new URLSearchParams({ company_id: String(companyId) });
  if (filter.bankAccountId !== undefined) {
    params.set("bank_account_id", String(filter.bankAccountId));
  }
  if (filter.from) params.set("from", filter.from);
  if (filter.to) params.set("to", filter.to);
  if (filter.statut) params.set("statut", filter.statut);
  if (filter.q?.trim()) params.set("q", filter.q.trim());
  if (filter.page !== undefined) params.set("page", String(filter.page));
  return `?${params}`;
}

/**
 * Écart d'un rapprochement manuel, en texte exact : opération + écriture. Un crédit en banque
 * correspond à un débit dans Sage, donc des montants de signes opposés : l'écart vaut « 0.00 »
 * quand les deux se compensent.
 */
export function ecartManuel(montantOperation: string, montantEcriture: string): string {
  return fromCents(toCents(montantOperation) + toCents(montantEcriture));
}

/** Un rapprochement manuel 1→1 exige le même montant, en sens opposé. */
export function rapprochable(montantOperation: string, montantEcriture: string): boolean {
  return (
    toCents(montantOperation) !== BigInt(0) &&
    ecartManuel(montantOperation, montantEcriture) === "0.00"
  );
}

/** Identifiants des propositions en attente que l'on peut valider en lot (fortes correspondances). */
export function fortes(correspondances: readonly Correspondance[]): number[] {
  return correspondances.filter((c) => c.statut === "Proposée" && c.forte).map((c) => c.id);
}

/** « 92.50 » → « 92,5 » ; « 100.00 » → « 100 ». */
export function formatScore(score: string | null): string {
  if (score === null) return "-";
  const [whole, decimals = ""] = score.split(".");
  const trimmed = decimals.replace(/0+$/, "");
  return trimmed ? `${whole},${trimmed}` : whole;
}

/** Montant absolu en texte exact (« -50000.00 » → « 50000.00 »). */
export function absolute(montant: string): string {
  return montant.startsWith("-") ? montant.slice(1) : montant;
}

/** Sens d'une opération bancaire, d'après son montant (crédit − débit). */
export function sensBanque(montant: string): "Crédit" | "Débit" {
  return montant.startsWith("-") ? "Débit" : "Crédit";
}

/** Clic sur un compteur : il devient le filtre, ou le retire s'il l'était déjà ("" = tous). */
export function toggleStatut(current: string, clicked: string): string {
  return current === clicked ? "" : clicked;
}
