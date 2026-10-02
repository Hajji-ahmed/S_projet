import { apiFetch } from "@/lib/api";
import type { Company, Currency } from "@/types/company";
import type { PointageType } from "@/types/statement";

export function listCompanies() {
  return apiFetch<Company[]>("/companies");
}

export function listCurrencies() {
  return apiFetch<Currency[]>("/currencies");
}

/** Types d'opération (Pointage) actifs, par libellé. */
export function listPointageTypes() {
  return apiFetch<PointageType[]>("/pointage-types");
}
