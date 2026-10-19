/** Import Sage et lecture des écritures (P10) : règles pures. Montants en texte exact. */

export type EntriesFilter = {
  bankAccountId?: number;
  from?: string;
  to?: string;
  statut?: string;
  q?: string;
  /** Type d'opération (14/10/2026). */
  typeOperation?: string;
  /** 19/10/2026 : false = sans opération bancaire possible, true = avec. */
  operationPossible?: boolean;
  page: number;
};

export const STATUTS_RAPPROCHEMENT = [
  "Non rapprochée",
  "À vérifier",
  "Rapprochée",
  "Écart",
] as const;

/**
 * Filtre Statut du volet Écritures du rapprochement (19/10/2026) : « Non rapprochée » ne montre
 * que les écritures sans opération bancaire possible ; celles qui en ont une sont à part.
 */
export const OPERATION_POSSIBLE = "Non rapprochée · opération possible";

export function statutEcritures(
  valeur: string,
): Pick<EntriesFilter, "statut" | "operationPossible"> {
  if (valeur === "Non rapprochée") return { statut: valeur, operationPossible: false };
  if (valeur === OPERATION_POSSIBLE) return { statut: "Non rapprochée", operationPossible: true };
  return { statut: valeur || undefined };
}

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
  if (filter.typeOperation) params.set("type_operation", filter.typeOperation);
  if (filter.operationPossible !== undefined) {
    params.set("operation_possible", String(filter.operationPossible));
  }
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
  /** Cases cochées (08/10/2026) : seules ces lignes sont importées ; remplace les deux options. */
  lignesChoisies?: number[];
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
  if (options.lignesChoisies) {
    form.append(
      "lignes_choisies",
      JSON.stringify([...options.lignesChoisies].sort((a, b) => a - b)),
    );
  }
  return form;
}
