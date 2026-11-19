/** Import Sage et lecture des écritures (P10) : règles pures. Montants en texte exact. */

import type { Ecriture } from "@/types/accounting";

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
  /** « Débit » ou « Crédit » de l'écriture (19/10/2026). */
  sens?: string;
  /** Tri par montant absolu (19/11/2026) : « montant_asc » ou « montant_desc » ; vide = par date. */
  tri?: string;
  page: number;
};

export const STATUTS_RAPPROCHEMENT = ["Non rapprochée", "À vérifier", "Rapprochée"] as const;

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
  if (filter.sens) params.set("sens", filter.sens);
  if (filter.tri) params.set("tri", filter.tri);
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
  /** Écritures absentes du grand livre à supprimer (05/11/2026), par id. */
  ecrituresSupprimees?: number[];
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
  if (options.ecrituresSupprimees?.length) {
    form.append(
      "ecritures_supprimees",
      JSON.stringify([...options.ecrituresSupprimees].sort((a, b) => a - b)),
    );
  }
  return form;
}

/** Correction d'une écriture (19/11/2026) : valeurs du formulaire, montants déjà normalisés. */
export type EcritureCorrigee = {
  libelle: string;
  reference: string;
  numero_piece: string;
  date_ecriture: string;
  echeance: string;
  debit: string | null;
  credit: string | null;
  /** Montant en devise, sans signe ; null hors compte EUR / USD. */
  montant_devise: string | null;
};

export type ChampsCorriges = Partial<{
  libelle: string;
  reference: string | null;
  numero_piece: string | null;
  date_ecriture: string;
  echeance: string | null;
  debit: string | null;
  credit: string | null;
  montant_devise: string | null;
}>;

/** « 38500 », « 38500.0 », « -38500.00 » → « 38500.00 » (sans passer par un float). */
function centimes(valeur: string | null | undefined): string {
  const [entier, decimales = ""] = (valeur ?? "0").replace("-", "").split(".");
  return `${entier.replace(/^0+(?=\d)/, "")}.${decimales.padEnd(2, "0")}`;
}

/** Seuls les champs qui changent. Débit et crédit partent ensemble ; sur un compte en devise, le
 * montant en devise accompagne toujours un changement de montant (le serveur l'exige). */
export function champsModifies(
  ecriture: Pick<
    Ecriture,
    | "libelle"
    | "reference"
    | "numero_piece"
    | "date_ecriture"
    | "echeance"
    | "debit"
    | "credit"
    | "montant_devise"
  >,
  saisie: EcritureCorrigee,
): ChampsCorriges {
  const champs: ChampsCorriges = {};
  const libelle = saisie.libelle.trim();
  if (libelle !== ecriture.libelle) champs.libelle = libelle;
  for (const cle of ["reference", "numero_piece"] as const) {
    const valeur = saisie[cle].trim() || null;
    if (valeur !== (ecriture[cle] ?? null)) champs[cle] = valeur;
  }
  if (saisie.date_ecriture !== ecriture.date_ecriture) champs.date_ecriture = saisie.date_ecriture;
  if ((saisie.echeance || null) !== (ecriture.echeance ?? null)) {
    champs.echeance = saisie.echeance || null;
  }
  const montantChange =
    centimes(saisie.debit) !== centimes(ecriture.debit) ||
    centimes(saisie.credit) !== centimes(ecriture.credit);
  if (montantChange) {
    champs.debit = saisie.debit;
    champs.credit = saisie.credit;
  }
  if (
    saisie.montant_devise !== null &&
    (montantChange || centimes(saisie.montant_devise) !== centimes(ecriture.montant_devise))
  ) {
    champs.montant_devise = saisie.montant_devise;
  }
  return champs;
}
