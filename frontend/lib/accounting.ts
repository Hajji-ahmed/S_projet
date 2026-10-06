/** Import Sage et lecture des écritures (P10) : règles pures. Montants en texte exact. */

export type EntriesFilter = {
  bankAccountId?: number;
  from?: string;
  to?: string;
  statut?: string;
  q?: string;
  page: number;
};

export const STATUTS_RAPPROCHEMENT = [
  "Non rapprochée",
  "À vérifier",
  "Rapprochée",
  "Écart",
] as const;

/** « ?company_id=…&… » : seuls les filtres renseignés, la page toujours. */
export function entriesQuery(companyId: number, filter: EntriesFilter): string {
  const params = new URLSearchParams({ company_id: String(companyId) });
  if (filter.bankAccountId !== undefined) {
    params.set("bank_account_id", String(filter.bankAccountId));
  }
  if (filter.from) params.set("from", filter.from);
  if (filter.to) params.set("to", filter.to);
  if (filter.statut) params.set("statut", filter.statut);
  if (filter.q?.trim()) params.set("q", filter.q.trim());
  params.set("page", String(filter.page));
  return `?${params}`;
}

/** Nombre de pages (au moins une, même sans écriture). */
export function pageCount(total: number, taille: number): number {
  return Math.max(1, Math.ceil(total / taille));
}

export type AccountingOptions = {
  mapping?: Record<string, number | null>;
  feuille?: string;
  garderDoublons?: number[];
  ecarterErreurs?: boolean;
};

/** Formulaire multipart de `/accounting/import/analyse` et `/confirm`. */
export function accountingForm(
  file: File,
  companyId: number,
  options: AccountingOptions = {},
): FormData {
  const form = new FormData();
  form.append("fichier", file);
  form.append("company_id", String(companyId));
  if (options.mapping) {
    const mapped = Object.fromEntries(
      Object.entries(options.mapping).filter(([, index]) => index !== null && index !== undefined),
    );
    form.append("mapping", JSON.stringify(mapped));
  }
  if (options.feuille) form.append("feuille", options.feuille);
  if (options.garderDoublons?.length) {
    form.append(
      "garder_doublons",
      JSON.stringify([...options.garderDoublons].sort((a, b) => a - b)),
    );
  }
  if (options.ecarterErreurs !== undefined) {
    form.append("ecarter_erreurs", String(options.ecarterErreurs));
  }
  return form;
}
