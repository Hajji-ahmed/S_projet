/** Comptabilisation des frais bancaires par SIMTIS : droits de timbre, commissions (13/10/2026). */

export type FamilleFrais = "timbres" | "commissions" | "frais";

/** Total d'un type dans l'écriture (commission, TVA, commission effet…). */
export type DetailFrais = {
  type: string;
  libelle: string;
  nb_operations: number;
  total: string;
};

/** Ligne de l'écriture au format du grand livre Sage ; `compte` null = à renseigner. */
export type LigneGL = {
  /** Type du frais (« commission », « tva »…), null pour la ligne banque. */
  type: string | null;
  type_libelle: string;
  /** Libellé exporté pour Sage : « COM », « TVA COM », « TVA FRAIS »… (14/10/2026). */
  libelle: string;
  compte: string | null;
  debit: string | null;
  credit: string | null;
};

export type Timbre = {
  id: number;
  date_operation: string;
  libelle: string;
  montant: string;
};

/** Écriture « DT D'ENREGISTREMENT » à passer : un jour, un compte, ses timbres (calculée). */
export type PropositionTimbres = {
  famille: FamilleFrais;
  bank_account_id: number;
  bank_code: string;
  bank_logo: string | null;
  devise: string;
  date: string;
  libelle: string;
  /** Montant de l'écriture, positif. */
  total: string;
  nb_operations: number;
  details: DetailFrais[];
  operations: Timbre[];
  /** Journal Sage des frais du compte (null : à renseigner). */
  journal: string | null;
  lignes: LigneGL[];
};

/** Écriture comptabilisée par SIMTIS et rapprochée de ses timbres. */
export type EcritureFrais = {
  /** « manuelle » : écriture saisie à la main (13/10/2026). */
  famille: FamilleFrais | "manuelle";
  id: number;
  bank_account_id: number;
  bank_code: string;
  date: string;
  journal: string | null;
  compte: string | null;
  libelle: string;
  montant: string;
  /** Code du rapprochement, aussi N° de pièce dans Sage. */
  code: string | null;
  /** N° pièce Sage AAMMNNN (15/10/2026). */
  numero_piece: string | null;
  nb_operations: number;
  exportee_le: string | null;
  lignes: LigneGL[];
};

/** Frais à comptabiliser à la main : une opération du relevé (13/10/2026). */
export type AutreFrais = {
  id: number;
  bank_account_id: number;
  bank_code: string;
  bank_logo: string | null;
  date_operation: string;
  libelle: string;
  montant: string;
  pointage: string | null;
};

/** Frais déjà dans une écriture Sage libre (13/10/2026) : à rapprocher, jamais à comptabiliser. */
export type FraisInclus = {
  id: number;
  bank_account_id: number;
  bank_code: string;
  bank_logo: string | null;
  date_operation: string;
  libelle: string;
  montant: string;
  ecriture: {
    id: number;
    date: string;
    journal: string | null;
    numero_piece: string | null;
    libelle: string;
    montant: string;
  };
};

export type Timbres = {
  autres_frais: AutreFrais[];
  frais_inclus?: FraisInclus[];
  propositions: PropositionTimbres[];
  total_propositions: string;
  ecritures: EcritureFrais[];
};

export type ValidationTimbres = {
  nb_ecritures: number;
  codes: string[];
};
