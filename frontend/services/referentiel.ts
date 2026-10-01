import { apiFetch } from "@/lib/api";
import type { Company, Currency } from "@/types/company";

export function listCompanies() {
  return apiFetch<Company[]>("/companies");
}

export function listCurrencies() {
  return apiFetch<Currency[]>("/currencies");
}
