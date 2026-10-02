/** Relevés bancaires (`backend/app/schemas/statement.py`). Montants en texte exact. */

/** Champ standard du relevé auquel une colonne du fichier peut être associée. */
export type FieldCode =
  | "date_operation"
  | "date_valeur"
  | "libelle"
  | "reference"
  | "debit"
  | "credit"
  | "montant"
  | "solde"
  | "pointage"
  | "lettrage_escompte"
  | "commentaire"
  | "banque";

/** Champ standard → index de colonne (0 = colonne A), ou null. */
export type ColumnMapping = Partial<Record<FieldCode, number | null>>;

export type ImportColumn = { index: number; lettre: string; entete: string; exemples: string[] };

export type ImportField = { code: FieldCode; libelle: string; obligatoire: boolean };

export type LineStatus = "Valide" | "Erreur" | "Doublon";

export type AnalysedLine = {
  numero: number;
  statut: LineStatus;
  motifs: string[];
  date_operation: string | null;
  date_valeur: string | null;
  libelle: string | null;
  reference: string | null;
  debit: string | null;
  credit: string | null;
  montant: string | null;
  solde: string | null;
  pointage: string | null;
  pointage_type_id: number | null;
  lettrage_escompte: string | null;
  commentaire: string | null;
  hash_ligne: string | null;
  /** Ligne identique plus haut dans le fichier : celle-ci peut être gardée. */
  doublon_de: number | null;
};

export type AnalysisSummary = {
  nb_lignes: number;
  nb_valides: number;
  nb_erreurs: number;
  nb_doublons: number;
  nb_ignorees: number;
  total_debit: string;
  total_credit: string;
  periode_debut: string | null;
  periode_fin: string | null;
  solde_ouverture: string | null;
  solde_cloture: string | null;
  soldes_coherents: boolean | null;
};

export type Analysis = {
  bank_account_id: number;
  company_id: number;
  bank_code: string;
  devise: string;
  fichier_nom: string;
  fichier_hash: string;
  deja_importe: boolean;
  feuilles: string[];
  feuille: string;
  ligne_entete: number;
  colonnes: ImportColumn[];
  champs: ImportField[];
  mapping: Record<FieldCode, number | null>;
  mapping_source: "Détection" | "Modèle de la banque" | "Utilisateur";
  erreurs_mapping: string[];
  lignes: AnalysedLine[];
  resume: AnalysisSummary;
};

export type BalanceCheck = {
  statut: "Conforme" | "Écart" | "À vérifier";
  date_controle: string;
  solde_releve: string;
  solde_enregistre: string;
  ecart: string;
  commentaire: string | null;
};

export type Confirmation = {
  import_id: number;
  statement_id: number;
  bank_account_id: number;
  fichier_nom: string;
  nb_importees: number;
  nb_erreurs_ecartees: number;
  nb_doublons_ecartes: number;
  total_debit: string;
  total_credit: string;
  periode_debut: string;
  periode_fin: string;
  solde_ouverture: string | null;
  solde_cloture: string | null;
  soldes_coherents: boolean | null;
  controle_solde: BalanceCheck | null;
  solde_du_jour: "Créé" | "Corrigé" | "Inchangé" | null;
  modele_enregistre: boolean;
};

export type Statement = {
  id: number;
  import_id: number;
  fichier_nom: string;
  importe_le: string;
  importe_par: string | null;
  bank_account_id: number;
  bank_code: string;
  devise: string;
  compte_libelle: string;
  compte_numero: string;
  periode_debut: string | null;
  periode_fin: string | null;
  solde_ouverture: string | null;
  solde_cloture: string | null;
  nb_lignes: number;
  nb_erreurs: number;
  nb_doublons: number;
  controle_solde: BalanceCheck | null;
};

/** Opération au format standard du relevé : ses 11 champs, puis référence, montant et statut. */
export type Transaction = {
  id: number;
  societe: string;
  /** Type d'opération ; null s'il est inconnu. */
  pointage: string | null;
  /** Code de la banque (AWB, BMCE...). */
  banque: string;
  date_operation: string;
  date_valeur: string | null;
  libelle: string;
  debit: string;
  credit: string;
  solde: string | null;
  lettrage_escompte: string | null;
  commentaire: string | null;
  reference: string | null;
  montant: string;
  statut: string;
};

/** Relevé continu d'un compte : toutes ses opérations importées, quel que soit le fichier. */
export type AccountStatement = {
  bank_account_id: number;
  societe: string;
  bank_code: string;
  devise: string;
  compte_libelle: string;
  compte_numero: string;
  periode_debut: string | null;
  periode_fin: string | null;
  nb_operations: number;
  total_debit: string;
  total_credit: string;
  solde_ouverture: string | null;
  solde_cloture: string | null;
  operations: Transaction[];
};

/** Ce que l'utilisateur envoie pour analyser, puis confirmer, un relevé. */
export type ImportRequest = {
  file: File;
  accountId: number;
  /** Absent : la correspondance est détectée (ou reprise du modèle de la banque). */
  mapping?: ColumnMapping;
  feuille?: string;
};

export type ConfirmOptions = { garderDoublons: number[]; ecarterErreurs: boolean };
