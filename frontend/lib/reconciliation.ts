/** Rapprochement 1→1 (P11) : règles pures de l'écran. Montants en texte exact, jamais en float. */
import { formatDate } from "@/lib/balances";
import { ECARTS_ACTIFS } from "@/lib/features";
import { fromCents, toCents } from "@/lib/statementLines";
import type { Ecriture, StatutRapprochement } from "@/types/accounting";
import type { Candidat, Correspondance, Operation } from "@/types/reconciliation";

export type ReconciliationFilter = {
  bankAccountId?: number;
  from: string;
  to: string;
  /** Type d'opération (14/10/2026) : Chèque, Effet, Espèces, Virement, Impayé ou Autre. */
  typeOperation?: string;
};

/** Filtre « Type » des volets et des propositions : mêmes règles que le moteur (14/10/2026). */
export const TYPES_OPERATION = [
  "Chèque",
  "Effet",
  "Espèces",
  "Virement",
  "Impayé",
  "Autre",
] as const;

export type TransactionsFilter = ReconciliationFilter & {
  statut?: string;
  /** « Débit » (argent sorti) ou « Crédit » (argent entré), 19/10/2026. */
  sens?: string;
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

/** Les deux dates d'une écriture sur les cartes des propositions (27/10/2026) : les espèces et
 * les virements se rapprochent par l'échéance. « Date 03/08/2026 · Échéance 05/08/2026 ». */
export function datesEcriture(ecriture: {
  date_ecriture: string;
  echeance: string | null;
}): string {
  return `Date ${formatDate(ecriture.date_ecriture)} · Échéance ${
    ecriture.echeance ? formatDate(ecriture.echeance) : "—"
  }`;
}

/** Période du rapprochement à l'ouverture (27/10/2026) : du 1er janvier de l'année en cours à
 * aujourd'hui. */
export function periodeRapprochement(today: string): { from: string; to: string } {
  return { from: `${today.slice(0, 4)}-01-01`, to: today };
}

/** Clé du navigateur où le rapprochement garde la dernière période choisie (27/10/2026). */
export const CLE_PERIODE = "simtis.rapprochement.periode";
const JOUR_ISO = /^\d{4}-\d{2}-\d{2}$/;
const PERIODE_MAX_JOURS = 1827; // comme l'API : 5 ans au plus

/** Ce que le navigateur garde : la période et le jour où elle a été choisie. */
export function periodeAStocker(periode: { from: string; to: string }, today: string): string {
  return JSON.stringify({ from: periode.from, to: periode.to, jour: today });
}

/**
 * Période reprise du navigateur, sinon celle de `periodeRapprochement`. Un « Au » qui était le jour
 * même du choix avance à aujourd'hui (sinon une période choisie « jusqu'à aujourd'hui » cacherait
 * les opérations des jours suivants) ; un « Au » choisi dans le passé reste tel quel. Une valeur
 * abîmée, inversée ou de plus de 5 ans est ignorée.
 */
export function periodeMemorisee(brut: string | null, today: string): { from: string; to: string } {
  const defaut = periodeRapprochement(today);
  if (!brut) return defaut;
  let lu: unknown;
  try {
    lu = JSON.parse(brut);
  } catch {
    return defaut;
  }
  if (typeof lu !== "object" || lu === null) return defaut;
  const { from, to, jour } = lu as Record<string, unknown>;
  if (![from, to, jour].every((v) => typeof v === "string" && JOUR_ISO.test(v))) return defaut;
  const fin = to === jour ? today : (to as string);
  const debut = from as string;
  if (debut > fin) return defaut;
  const jours = (Date.parse(`${fin}T00:00:00Z`) - Date.parse(`${debut}T00:00:00Z`)) / 86_400_000;
  if (!Number.isFinite(jours) || jours >= PERIODE_MAX_JOURS) return defaut;
  return { from: debut, to: fin };
}

/** « ?company_id=…&… » : seuls les filtres renseignés ; `page` seulement si demandée. */
/** Filtre du volet : frais bancaires non rapprochés, à passer dans Sage (12/10/2026). */
export const A_COMPTABILISER = "À comptabiliser";

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
  // « À comptabiliser » n'est pas un statut : un filtre sur les frais bancaires non rapprochés
  if (filter.statut === A_COMPTABILISER) params.set("a_comptabiliser", "true");
  else if (filter.statut) params.set("statut", filter.statut);
  if (filter.sansAVerifier) params.set("sans_a_verifier", "true");
  if (filter.q?.trim()) params.set("q", filter.q.trim());
  if (filter.typeOperation) params.set("type_operation", filter.typeOperation);
  if (filter.sens) params.set("sens", filter.sens);
  if (filter.page !== undefined) params.set("page", String(filter.page));
  return `?${params}`;
}

/** Filtre « Sens » des deux volets (19/10/2026). */
export const SENS_VOLET = ["Débit", "Crédit"] as const;

/**
 * Dates propres à un volet (19/10/2026), bornées par la période de l'écran : elles ne font que la
 * réduire. Vides = toute la période. `ajustee` : une date sortait de la période ou Du > Au.
 */
export function bornerPeriode(
  periode: { from: string; to: string },
  du: string,
  au: string,
): { from: string; to: string; ajustee: boolean } {
  let from = du && du > periode.from ? du : periode.from;
  let to = au && au < periode.to ? au : periode.to;
  let ajustee = (du !== "" && du < periode.from) || (au !== "" && au > periode.to);
  if (from > to) {
    from = periode.from;
    to = periode.to;
    ajustee = true;
  }
  return { from, to, ajustee };
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
  return (
    item.statut === "Proposée" && rapprochable(montantBanque(item), montantEcriture(item.ecriture))
  );
}

/** Une proposition encore en attente se rejette, même si ses montants diffèrent (27/10/2026). */
export function rejetable(item: Correspondance): boolean {
  return item.statut === "Proposée";
}

/** Propositions cochées que « Valider la sélection » envoie : les validables seulement. */
export function aValider(
  items: readonly Correspondance[],
  selected: ReadonlySet<number>,
): Correspondance[] {
  return items.filter((item) => selected.has(item.id) && validable(item));
}

/** Propositions que « Rejeter la sélection » envoie (27/10/2026) : cochées ET affichées par le
 *  filtre en cours ; une proposition cochée mais cachée par le filtre n'est jamais rejetée. */
export function aRejeter(
  shown: readonly Correspondance[],
  selected: ReadonlySet<number>,
): Correspondance[] {
  return shown.filter((item) => selected.has(item.id) && rejetable(item));
}

/** Sélection proposée à l'ouverture : seules les fortes validables sans concurrente proche sont
 *  cochées d'office (08/10/2026) ; les autres se cochent après contrôle. */
export function defaultSelection(items: readonly Correspondance[]): Set<number> {
  return new Set(
    items
      .filter((item) => item.forte && !item.concurrente_proche && !item.elargie && validable(item))
      .map((item) => item.id),
  );
}

export type ProposalsFilter =
  "toutes" | "fortes" | "a_verifier" | "ambigues" | "ecritures_ambigues" | "eloignees";

/** Filtre Toutes · Fortes (≥ seuil) · À vérifier (< seuil), la plus forte d'abord. */
export function filterProposals(
  items: readonly Correspondance[],
  filtre: ProposalsFilter,
): Correspondance[] {
  return items
    .filter(
      (item) =>
        filtre === "toutes" ||
        (filtre === "eloignees" && !!item.elargie) ||
        (filtre !== "ambigues" &&
          filtre !== "eloignees" &&
          filtre !== "ecritures_ambigues" &&
          (filtre === "fortes") === item.forte),
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
    (sum, item) => sum + toCents(absolute(montantBanque(item))),
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

export const STATUTS_VOLET: string[] = [...statutsVolet(ECARTS_ACTIFS), A_COMPTABILISER];

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
      rapprochable(montantOperation, montantEcriture(candidat.ecriture)) ||
      toCents(candidat.score) >= seuil;
    (utile ? utiles : autres).push(candidat);
  }
  return { utiles, autres };
}

/** Propositions au plus par validation en lot, comme le serveur (`LOT_MAX`, 10 000 depuis le 12/10/2026). */
export const LOT_MAX = 10000;

/** Opérations d'une correspondance : plusieurs pour un groupe N → 1 (12/10/2026), sinon une. */
export function operationsDe(item: Correspondance): Operation[] {
  return item.operations?.length ? item.operations : [item.operation];
}

/** Montant côté banque : le total d'un groupe, sinon celui de l'opération. */
export function montantBanque(item: Correspondance): string {
  return operationsDe(item).length > 1 && item.total_operations
    ? item.total_operations
    : item.operation.montant;
}

/** Écritures d'une correspondance : plusieurs en 1 → N et N → N (P13, 15/10/2026), sinon une. */
export function ecrituresDe(item: Correspondance): Ecriture[] {
  return item.ecritures?.length ? item.ecritures : [item.ecriture];
}

/** Nombre d'opérations et d'écritures d'une correspondance, y compris celles que l'API ne renvoie
 * pas (au plus 20 par côté, 27/10/2026 : une reprise en compte des milliers). */
export function nbOperations(item: Correspondance): number {
  return Math.max(item.nb_operations ?? 0, operationsDe(item).length);
}

export function nbEcritures(item: Correspondance): number {
  return Math.max(item.nb_ecritures ?? 0, ecrituresDe(item).length);
}

/** Montant côté Sage : le total des écritures quand il y en a plusieurs, sinon celui de l'écriture
 * (en devise pour un compte EUR / USD). */
export function montantSage(item: Correspondance): string {
  return ecrituresDe(item).length > 1 && item.total_ecritures
    ? item.total_ecritures
    : montantEcriture(item.ecriture);
}

/** « lettrage-2026-09-01-2026-10-14.xlsx » : le nom proposé au téléchargement. */
export function lettrageFilename(filter: ReconciliationFilter): string {
  return `lettrage-${filter.from}-${filter.to}.xlsx`;
}

/** Unité affichée d'un montant : « DH » pour le MAD, sinon le code de la devise (14/10/2026). */
export function unite(devise?: string | null): string {
  return !devise || devise === "MAD" ? "DH" : devise;
}

/** Montant d'une écriture face au relevé : en devise pour un compte EUR / USD (colonne « Devise »
 * de Sage), sinon le montant MAD. Comme `montant_rapprochement` côté serveur. */
export function montantEcriture(ecriture: {
  montant: string;
  montant_devise?: string | null;
}): string {
  return ecriture.montant_devise ?? ecriture.montant;
}

/** Unité du montant de rapprochement d'une écriture : sa devise si elle a un montant devise. */
export function uniteEcriture(ecriture: {
  montant_devise?: string | null;
  devise?: string | null;
}): string {
  return ecriture.montant_devise != null ? unite(ecriture.devise) : "DH";
}

// --- Rapprochement manuel de plusieurs lignes (P13, 15/10/2026) -----------------------------------

/** Au plus 50 lignes de chaque côté (même règle que l'API). */
export const MANUEL_MAX = 50;

export type BlocagePanier = "vide" | "limite" | "comptes" | "rapprochee" | "ecart" | null;

export type EtatPanier = {
  /** Totaux signés, en texte exact, dans la devise du compte. */
  totalBanque: string;
  totalSage: string;
  /** Total banque + total Sage : « 0.00 » quand ils se compensent. */
  ecart: string;
  type: "1-1" | "1-N" | "N-1" | "N-N";
  devise: string | undefined;
  /** Pourquoi le rapprochement n'est pas encore possible ; null = prêt. */
  blocage: BlocagePanier;
};

type LignePanier = { bank_account_id: number | null; statut: string; devise?: string | null };

/** Totaux, écart et type d'un panier de lignes choisies à la main ; mêmes règles que l'API. */
export function etatPanier(
  operations: readonly (LignePanier & { montant: string })[],
  ecritures: readonly (LignePanier & { montant: string; montant_devise?: string | null })[],
): EtatPanier {
  const totalBanque = operations.reduce((total, op) => total + toCents(op.montant), BigInt(0));
  const totalSage = ecritures.reduce(
    (total, ecriture) => total + toCents(montantEcriture(ecriture)),
    BigInt(0),
  );
  const ecart = totalBanque + totalSage;
  const comptes = new Set([...operations, ...ecritures].map((ligne) => ligne.bank_account_id));
  const type =
    `${operations.length > 1 ? "N" : "1"}-${ecritures.length > 1 ? "N" : "1"}` as EtatPanier["type"];
  let blocage: BlocagePanier = null;
  if (operations.length === 0 || ecritures.length === 0) blocage = "vide";
  else if (operations.length > MANUEL_MAX || ecritures.length > MANUEL_MAX) blocage = "limite";
  else if (comptes.size > 1) blocage = "comptes";
  else if ([...operations, ...ecritures].some((ligne) => ligne.statut === "Rapprochée"))
    blocage = "rapprochee";
  else if (ecart !== BigInt(0)) blocage = "ecart";
  return {
    totalBanque: fromCents(totalBanque),
    totalSage: fromCents(totalSage),
    ecart: fromCents(ecart),
    type,
    devise: operations[0]?.devise ?? ecritures[0]?.devise ?? undefined,
    blocage,
  };
}

/** Ajoute la ligne au panier, ou l'en retire si elle y est déjà. */
export function basculerLigne<T extends { id: number }>(lignes: readonly T[], ligne: T): T[] {
  return lignes.some((l) => l.id === ligne.id)
    ? lignes.filter((l) => l.id !== ligne.id)
    : [...lignes, ligne];
}
