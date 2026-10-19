import { apiDownload, apiFetch } from "@/lib/api";
import type { ReconciliationFilter } from "@/lib/reconciliation";
import type { FamilleFrais, ModificationFrais, Timbres, ValidationTimbres } from "@/types/frais";

const JSON_HEADERS = { "Content-Type": "application/json" };

function query(companyId: number, filter: ReconciliationFilter, extra?: Record<string, string>) {
  const params = new URLSearchParams({ company_id: String(companyId) });
  if (filter.bankAccountId !== undefined)
    params.set("bank_account_id", String(filter.bankAccountId));
  if (filter.from) params.set("from", filter.from);
  if (filter.to) params.set("to", filter.to);
  for (const [key, value] of Object.entries(extra ?? {})) params.set(key, value);
  return `?${params}`;
}

/** Tableau unique : écritures à passer (calculées) et écritures déjà comptabilisées par SIMTIS,
 * droits de timbre et commissions. */
export function listFrais(companyId: number, filter: ReconciliationFilter) {
  return apiFetch<Timbres>(`/frais${query(companyId, filter)}`);
}

/** Comptabilise les jours choisis : écritures créées et rapprochées d'emblée (tous ou aucun). */
export function validerFrais(
  companyId: number,
  jours: ({ famille: FamilleFrais; bank_account_id: number; date: string } & ModificationFrais)[],
) {
  return apiFetch<ValidationTimbres>("/frais/valider", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ company_id: companyId, jours }),
  });
}

/** UN fichier CSV pour Sage (16/10/2026), toutes familles de frais ; les écritures exportées ne se
 * suppriment plus. */
export function exporterFrais(companyId: number, filter: ReconciliationFilter, deja = false) {
  return apiDownload(
    `/frais/export${query(companyId, filter, deja ? { inclure_exportees: "true" } : {})}`,
  );
}

/** Supprime une écriture SIMTIS pas encore exportée ; ses opérations redeviennent à comptabiliser. */
export function supprimerEcritureFrais(entryId: number, motif: string) {
  return apiFetch<void>(`/frais/ecritures/${entryId}`, {
    method: "DELETE",
    headers: JSON_HEADERS,
    body: JSON.stringify({ motif }),
  });
}

/** Écriture saisie à la main pour des frais d'un même compte, TVA séparée ou non (13/10/2026). */
export function comptabiliserManuellement(body: {
  company_id: number;
  transaction_ids: number[];
  libelle: string;
  date: string;
  taux_tva: string | null;
  montant_tva: string | null;
}) {
  return apiFetch<ValidationTimbres>("/frais/manuelle", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
}

type JourChoisi = { famille: FamilleFrais; bank_account_id: number; date: string };

/** Écarte des journées proposées (19/10/2026) : leurs frais passent à la main. */
export function ecarterFrais(companyId: number, jours: JourChoisi[], motif?: string) {
  return apiFetch<{ nb: number }>("/frais/ecarter", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ company_id: companyId, jours, motif: motif?.trim() || null }),
  });
}

/** Annule l'écartement : SIMTIS propose de nouveau ces journées. */
export function reproposerFrais(companyId: number, jours: JourChoisi[]) {
  return apiFetch<{ nb: number }>("/frais/reproposer", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ company_id: companyId, jours }),
  });
}
