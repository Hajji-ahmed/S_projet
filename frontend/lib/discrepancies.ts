/** Écarts (P12) : règles pures, mêmes que `backend/app/services/discrepancy_service.py`. */
import { ecartManuel } from "@/lib/reconciliation";
import type { StatutEcart, TypeEcart } from "@/types/discrepancy";

export type DiscrepanciesFilter = {
  statut?: string;
  type?: string;
  responsableId?: number;
  bankAccountId?: number;
  from?: string;
  to?: string;
  q?: string;
  page: number;
};

/** « ?company_id=…&… » : seuls les filtres renseignés, la page toujours. */
export function discrepanciesQuery(companyId: number, filter: DiscrepanciesFilter): string {
  const params = new URLSearchParams({ company_id: String(companyId) });
  if (filter.statut) params.set("statut", filter.statut);
  if (filter.type) params.set("type", filter.type);
  if (filter.responsableId !== undefined) {
    params.set("responsable_id", String(filter.responsableId));
  }
  if (filter.bankAccountId !== undefined) {
    params.set("bank_account_id", String(filter.bankAccountId));
  }
  if (filter.from) params.set("from", filter.from);
  if (filter.to) params.set("to", filter.to);
  if (filter.q?.trim()) params.set("q", filter.q.trim());
  params.set("page", String(filter.page));
  return `?${params}`;
}

/**
 * Lignes de chaque type : opération puis écriture ; true = obligatoire, false = interdite,
 * null = facultative. « Doublon potentiel » porte sur une seule ligne, l'une ou l'autre.
 */
export const LIGNES_PAR_TYPE: Record<TypeEcart, [boolean | null, boolean | null]> = {
  "Banque sans écriture": [true, false],
  "Écriture sans banque": [false, true],
  "Montant différent": [true, true],
  "Date différente": [true, true],
  "Libellé ambigu": [true, null],
  "Doublon potentiel": [null, null],
};

/** Motif qui empêche de signaler cet écart avec ces lignes, sinon null. */
export function typeProblem(
  type: TypeEcart,
  operation: { montant: string } | null,
  ecriture: { montant: string } | null,
): string | null {
  if (type === "Doublon potentiel") {
    return (operation === null) === (ecriture === null)
      ? "Un doublon potentiel porte sur une seule ligne : une opération ou une écriture."
      : null;
  }
  const [withOperation, withEcriture] = LIGNES_PAR_TYPE[type];
  if (withOperation === true && !operation) return "Sélectionnez une opération bancaire.";
  if (withEcriture === true && !ecriture) return "Sélectionnez une écriture comptable.";
  if (withOperation === false && operation) return "Ce type ne porte pas sur une opération.";
  if (withEcriture === false && ecriture) return "Ce type ne porte pas sur une écriture.";
  if (type === "Montant différent" && operation && ecriture) {
    if (ecartManuel(operation.montant, ecriture.montant) === "0.00") {
      return "Les montants s'équilibrent : ce n'est pas un écart de montant.";
    }
  }
  return null;
}

/** Type proposé selon les lignes sélectionnées. */
export function suggestedType(
  operation: { montant: string } | null,
  ecriture: { montant: string } | null,
): TypeEcart {
  if (operation && ecriture) {
    return ecartManuel(operation.montant, ecriture.montant) === "0.00"
      ? "Date différente"
      : "Montant différent";
  }
  return ecriture ? "Écriture sans banque" : "Banque sans écriture";
}

/** Statuts atteignables depuis un statut ouvert (la clôture a sa propre action). */
export function nextStatuses(statut: StatutEcart): StatutEcart[] {
  switch (statut) {
    case "À traiter":
      return ["En cours"];
    case "En cours":
      return ["Traité"];
    case "Traité":
      return ["En cours"];
    default:
      return [];
  }
}

/** Montants ouverts par devise : MAD d'abord, puis les autres par code. */
export function openTotals(montants: Record<string, string>): [string, string][] {
  return Object.entries(montants).sort(([a], [b]) =>
    a === "MAD" ? -1 : b === "MAD" ? 1 : a.localeCompare(b),
  );
}

const ACTIONS: Record<string, string> = {
  creation_ecart: "Écart créé",
  modification_ecart: "Écart modifié",
  cloture_ecart: "Écart clôturé",
};

/** Libellé d'un événement de l'historique ; « origine Automatique » est précisée. */
export function eventLabel(action: string, apres: Record<string, unknown> | null): string {
  const label = ACTIONS[action] ?? action;
  return apres?.origine === "Automatique" ? `${label} automatiquement` : label;
}

const CHAMPS: Record<string, string> = {
  statut: "Statut",
  responsable_id: "Responsable",
  commentaire: "Commentaire",
};

/** Champs changés par une modification, dans l'ordre d'affichage. */
export function changedFields(
  avant: Record<string, unknown> | null,
  apres: Record<string, unknown> | null,
): string[] {
  if (!avant || !apres) return [];
  return Object.keys(CHAMPS)
    .filter((key) => JSON.stringify(avant[key]) !== JSON.stringify(apres[key]))
    .map((key) => CHAMPS[key]);
}
