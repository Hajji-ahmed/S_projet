import { apiFetch } from "@/lib/api";
import type {
  DetailHistorique,
  FiltresHistorique,
  PageHistorique,
  RechercheHistorique,
} from "@/types/historique";

/** Journal d'audit filtré, 50 lignes par page, du plus récent au plus ancien. */
export function getHistorique(recherche: RechercheHistorique) {
  const params = new URLSearchParams({ page: String(recherche.page) });
  for (const cle of ["user_id", "action", "entite", "from", "to"] as const) {
    if (recherche[cle]) params.set(cle, recherche[cle]);
  }
  return apiFetch<PageHistorique>(`/audit?${params}`);
}

export function getDetailHistorique(id: number) {
  return apiFetch<DetailHistorique>(`/audit/${id}`);
}

export function getFiltresHistorique() {
  return apiFetch<FiltresHistorique>("/audit/filtres");
}
