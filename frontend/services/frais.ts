import { apiDownload, apiFetch } from "@/lib/api";
import type { ReconciliationFilter } from "@/lib/reconciliation";
import type {
  AExporter,
  CompteFrais,
  FamilleFrais,
  ModificationFrais,
  Timbres,
  ValidationTimbres,
} from "@/types/frais";

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

/** Écriture choisie : sa famille, son compte, son jour et son opération (une écriture par frais,
 * 13/11/2026 ; sans opération, toute la journée). */
type JourChoisi = {
  famille: FamilleFrais;
  bank_account_id: number;
  date: string;
  transaction_id?: number | null;
};

/** Comptabilise les écritures choisies : créées et rapprochées d'emblée (toutes ou aucune). */
export function validerFrais(companyId: number, jours: (JourChoisi & ModificationFrais)[]) {
  return apiFetch<ValidationTimbres>("/frais/valider", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ company_id: companyId, jours }),
  });
}

/** Ce qui reste à exporter vers Sage, par banque et par mois (09/11/2026). */
export function listerAExporter(companyId: number) {
  return apiFetch<AExporter[]>(`/frais/a-exporter?company_id=${companyId}`);
}

/** UN fichier CSV pour Sage par banque et par mois (09/11/2026), numéroté à partir de la première
 * pièce saisie ; chaque écriture ne s'exporte qu'une fois et ne se supprime plus ensuite. */
export function exporterFrais(companyId: number, bankId: number, mois: string, premiere: string) {
  const params = new URLSearchParams({
    company_id: String(companyId),
    bank_id: String(bankId),
    mois,
    premiere_piece: premiere,
  });
  return apiDownload(`/frais/export?${params}`);
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
  /** Compte de charge choisi (05/11/2026) ; absent : d'après le libellé. */
  compte?: string;
}) {
  return apiFetch<ValidationTimbres>("/frais/manuelle", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
}

/** Comptes de charge des frais bancaires (05/11/2026), à choisir pour une écriture manuelle. */
export function listComptesFrais() {
  return apiFetch<CompteFrais[]>("/frais/comptes");
}

/** Écarte des frais proposés (13/11/2026 ; des journées le 19/10/2026) : ils passent à la main. */
export function ecarterFrais(companyId: number, jours: JourChoisi[], motif?: string) {
  return apiFetch<{ nb: number }>("/frais/ecarter", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ company_id: companyId, jours, motif: motif?.trim() || null }),
  });
}

/** Annule l'écartement : SIMTIS propose de nouveau ces frais ou ces journées. */
export function reproposerFrais(companyId: number, jours: JourChoisi[]) {
  return apiFetch<{ nb: number }>("/frais/reproposer", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ company_id: companyId, jours }),
  });
}

/** Excel des frais de plus de 200 DH (hors droits de timbre) à justifier auprès de la banque
 * (19/10/2026) ; rien n'est marqué, il se retélécharge. */
export function exporterJustificatif(companyId: number, filter: ReconciliationFilter) {
  return apiDownload(`/frais/justificatif${query(companyId, filter)}`);
}
