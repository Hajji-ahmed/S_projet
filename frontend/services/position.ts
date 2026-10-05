import { apiFetch } from "@/lib/api";
import type { BanquesTable, DevisesSoldes } from "@/types/position";

/** Lignes EUR et USD du tableau Devises (soldes des comptes en devise) jusqu'à une date. */
export function getDevisesSoldes(companyId: number, jour: string) {
  const query = new URLSearchParams({ company_id: String(companyId), date: jour });
  return apiFetch<DevisesSoldes>(`/position/devises/soldes?${query}`);
}

/** Tableau Banques calculé d'une société jusqu'à une date (« AAAA-MM-JJ »). */
export function getBanquesTable(companyId: number, jour: string) {
  const query = new URLSearchParams({ company_id: String(companyId), date: jour });
  return apiFetch<BanquesTable>(`/position/banques?${query}`);
}
