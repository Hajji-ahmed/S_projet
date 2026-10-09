/** Rapprochement 1→1 (P11) : règles pures de l'écran. Montants en texte exact, jamais en float. */
import { ECARTS_ACTIFS } from "@/lib/features";
import { fromCents, toCents } from "@/lib/statementLines";
import type { StatutRapprochement } from "@/types/accounting";
import type { Candidat, Correspondance, Operation } from "@/types/reconciliation";

export type ReconciliationFilter = {
  bankAccountId?: number;
  from: string;
  to: string;
};

export type TransactionsFilter = ReconciliationFilter & {
  statut?: string;
  /** Ne pas lister les opérations « À vérifier » : elles sont dans l'onglet Propositions. */
  sansAVerifier?: boolean;
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
  if (filter.sansAVerifier) params.set("sans_a_verifier", "true");
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

/** Une proposition validable : en attente et équilibrée (même montant, sens opposé). */
export function validable(item: Correspondance): boolean {
  return item.statut === "Proposée" && rapprochable(item.operation.montant, item.ecriture.montant);
}

/** Sélection proposée à l'ouverture : seules les fortes validables sans concurrente proche sont
 *  cochées d'office (08/10/2026) ; les autres se cochent après contrôle. */
export function defaultSelection(items: readonly Correspondance[]): Set<number> {
  return new Set(
    items
      .filter((item) => item.forte && !item.concurrente_proche && validable(item))
      .map((item) => item.id),
  );
}

export type ProposalsFilter = "toutes" | "fortes" | "a_verifier" | "ambigues";

/** Filtre Toutes · Fortes (≥ seuil) · À vérifier (< seuil), la plus forte d'abord. */
export function filterProposals(
  items: readonly Correspondance[],
  filtre: ProposalsFilter,
): Correspondance[] {
  return items
    .filter(
      (item) =>
        filtre === "toutes" || (filtre !== "ambigues" && (filtre === "fortes") === item.forte),
    )
    .sort((a, b) => {
      const diff = toCents(b.score ?? "0") - toCents(a.score ?? "0");
      return diff > BigInt(0) ? 1 : diff < BigInt(0) ? -1 : a.id - b.id;
    });
}

/** Résumé de la sélection : nombre, nombre de faibles et total des opérations (centimes exacts). */
export function selectionSummary(
  items: readonly Correspondance[],
  selected: ReadonlySet<number>,
): { nb: number; faibles: number; total: string } {
  const chosen = items.filter((item) => selected.has(item.id));
  const total = chosen.reduce(
    (sum, item) => sum + toCents(absolute(item.operation.montant)),
    BigInt(0),
  );
  return {
    nb: chosen.length,
    faibles: chosen.filter((item) => !item.forte).length,
    total: fromCents(total),
  };
}

/** L'opération d'une proposition, avec sa correspondance : le panneau central l'affiche. */
export function operationOf(item: Correspondance): Operation {
  return {
    ...item.operation,
    correspondance: {
      id: item.id,
      statut: item.statut,
      origine: item.origine,
      score: item.score,
      ecriture_id: item.ecriture.id,
    },
  };
}

/**
 * Sens d'une écriture dans Sage, d'après son montant (crédit − débit) : un montant positif est un
 * crédit du compte banque (argent qui sort), un montant négatif un débit (argent qui entre).
 */
export function sensSage(montant: string): "crédit Sage" | "débit Sage" {
  return montant.startsWith("-") ? "débit Sage" : "crédit Sage";
}

/**
 * Statuts du filtre du volet « Transactions bancaires » : « À vérifier » est dans Propositions, et
 * « Écart » seulement quand la fonction Écarts est active.
 */
export function statutsVolet(ecartsActifs: boolean): StatutRapprochement[] {
  return ecartsActifs
    ? ["Non rapprochée", "Rapprochée", "Écart"]
    : ["Non rapprochée", "Rapprochée"];
}

export const STATUTS_VOLET = statutsVolet(ECARTS_ACTIFS);

/**
 * Écritures possibles d'une opération (09/10/2026) : « utiles » = même montant (rapprochables) ou
 * score au moins égal au seuil de proposition ; les autres (même jour, sans rapport) sont repliées.
 */
export function trierCandidats(
  montantOperation: string,
  candidats: readonly Candidat[],
  seuilProposition: string,
): { utiles: Candidat[]; autres: Candidat[] } {
  const seuil = toCents(seuilProposition);
  const utiles: Candidat[] = [];
  const autres: Candidat[] = [];
  for (const candidat of candidats) {
    const utile =
      rapprochable(montantOperation, candidat.ecriture.montant) || toCents(candidat.score) >= seuil;
    (utile ? utiles : autres).push(candidat);
  }
  return { utiles, autres };
}
