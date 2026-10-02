import { apiFetch } from "@/lib/api";
import type { Devises, DevisesInput, Previsions, PrevisionsInput } from "@/types/saisie";

function query(companyId: number, jour: string) {
  return `?${new URLSearchParams({ company_id: String(companyId), date: jour })}`;
}

function put<T>(path: string, data: unknown) {
  return apiFetch<T>(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

/** Grille Devises d'une société pour une date (« AAAA-MM-JJ »). */
export function getDevises(companyId: number, jour: string) {
  return apiFetch<Devises>(`/position/devises${query(companyId, jour)}`);
}

/** Remplace la grille Devises de la date : une cellule absente est vidée. */
export function saveDevises(companyId: number, jour: string, data: DevisesInput) {
  return put<Devises>(`/position/devises${query(companyId, jour)}`, data);
}

export function getPrevisions(companyId: number, jour: string) {
  return apiFetch<Previsions>(`/position/previsions${query(companyId, jour)}`);
}

/** Remplace la grille Prévisions de la date : une cellule absente est vidée. */
export function savePrevisions(companyId: number, jour: string, data: PrevisionsInput) {
  return put<Previsions>(`/position/previsions${query(companyId, jour)}`, data);
}
