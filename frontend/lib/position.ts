import { finNumero } from "@/lib/accounts";
/**
 * Affichage des tableaux Banques et Devises. Les montants restent en texte exact : rien n'est
 * recalculé ici.
 */
import { formatDate } from "@/lib/balances";
import { formatAmount } from "@/lib/format";

/** Jours « facilité de caisse » visibles d'abord ; les plus anciens derrière « Afficher plus ». */
export const JOURS_AFFICHES = 10;

/** Taux en % : « 5.5 » → « 5,50 % » (deux décimales au moins, jamais tronqué) ; absent → « - ». */
export function formatTaux(pct: string | null): string {
  if (pct === null) return "-";
  const [entier, decimales = ""] = pct.split(".");
  return `${entier},${decimales.padEnd(2, "0")} %`;
}

/**
 * Cellule EUR / USD du tableau Devises : le solde dans sa devise, jamais converti (décision du
 * 05/10/2026), avec la date d'un solde repris d'un jour précédent. Inconnu → « - », jamais 0.
 */
export type CelluleNote = {
  valeur: string | null;
  date_solde: string | null;
  reprise: boolean;
  detail?: { numero: string; solde: string }[];
};

/**
 * Infobulle d'une cellule : le solde de chaque compte quand la banque en a plusieurs dans la devise
 * (23/10/2026), puis la date d'un dernier solde repris ; `null` s'il n'y a rien à dire.
 */
export function noteCellule(cellule: CelluleNote, devise?: string): string | null {
  const parties: string[] = [];
  if (cellule.detail && cellule.detail.length > 1) {
    const comptes = cellule.detail
      .map((compte) => `${finNumero(compte.numero)} : ${formatAmount(compte.solde, devise)}`)
      .join(" ; ");
    parties.push(`Somme de ${cellule.detail.length} comptes (soldes ${comptes})`);
  }
  if (cellule.reprise) parties.push(`dernier solde connu : ${formatDate(cellule.date_solde)}`);
  return parties.length > 0 ? parties.join(" · ") : null;
}

export function currencyCell(
  cellule: { bank_id?: number } & CelluleNote,
  devise: string,
): { text: string; note: string | null } {
  return { text: formatAmount(cellule.valeur, devise), note: noteCellule(cellule, devise) };
}

/** « 2026-09-30 » → « 30/09/26 », comme les dates du classeur. */
export function formatJour(iso: string): string {
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year.slice(2)}`;
}

/** Jours tracés par le graphique « Évolution de la position ». */
export const JOURS_GRAPHIQUE = 30;

export type EvolutionPoint = {
  date: string;
  /** « jj/mm » pour l'axe. */
  label: string;
  /** Valeur à tracer : conversion pour le dessin seulement, aucun calcul n'est fait dessus. */
  total: number | null;
  /** Montant exact de l'API, affiché dans l'infobulle. */
  totalText: string | null;
};

/**
 * Points du graphique des `count` derniers jours, du plus ancien au plus récent : le TOTAL, ou la
 * facilité de caisse d'une banque (`bankId`). Une valeur absente reste `null` (un vide dans la
 * courbe), jamais 0.
 */
export function evolutionPoints(
  jours: readonly {
    date: string;
    total: string | null;
    cellules?: readonly { bank_id: number; valeur: string | null }[];
  }[],
  count: number,
  bankId: number | null = null,
): EvolutionPoint[] {
  return jours.slice(-count).map((day) => {
    const [, month, dayOfMonth] = day.date.split("-");
    const text =
      bankId === null
        ? day.total
        : (day.cellules?.find((cellule) => cellule.bank_id === bankId)?.valeur ?? null);
    return {
      date: day.date,
      label: `${dayOfMonth}/${month}`,
      total: text === null ? null : Number(text),
      totalText: text,
    };
  });
}

export type Tone = "positive" | "negative" | "neutral";

/** Signe d'un montant exact, pour la couleur de Disponible Fc reel (vert > 0, rouge < 0). */
export function signTone(value: string | null): Tone {
  if (value === null || /^-?0*(\.0*)?$/.test(value)) return "neutral";
  return value.startsWith("-") ? "negative" : "positive";
}
