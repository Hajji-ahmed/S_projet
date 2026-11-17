import { apiFetch } from "@/lib/api";
import type {
  Company,
  CompanyAdmin,
  CompanyCreate,
  CompanyUpdate,
  Currency,
} from "@/types/company";
import type { PointageType } from "@/types/statement";

const JSON_HEADERS = { "Content-Type": "application/json" };

export function listCompanies() {
  return apiFetch<Company[]>("/companies");
}

/** Toutes les sociétés, y compris désactivées (permission `admin.settings`). */
export function listAllCompanies() {
  return apiFetch<CompanyAdmin[]>("/companies/toutes");
}

export function createCompany(data: CompanyCreate) {
  return apiFetch<CompanyAdmin>("/companies", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });
}

export function updateCompany(id: number, data: CompanyUpdate) {
  return apiFetch<CompanyAdmin>(`/companies/${id}`, {
    method: "PATCH",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });
}

export function listCurrencies() {
  return apiFetch<Currency[]>("/currencies");
}

/** Types d'opération (Pointage) actifs, par libellé. */
export function listPointageTypes() {
  return apiFetch<PointageType[]>("/pointage-types");
}
