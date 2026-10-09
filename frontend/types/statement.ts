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
  /** Fichier sans soldes : solde calculé depuis le solde d'ouverture choisi (aperçu). */
  solde_apercu: string | null;
  /** Valeur lue dans le fichier, telle quelle. */
  pointage: string | null;
  pointage_type_id: number | null;
  pointage_libelle: string | null;
  /** Déduit du libellé et du sens (pas de valeur connue dans le fichier). */
  pointage_auto: boolean;
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
  /** Lu sur une ligne SOLDE INITIAL (ou SOLDE FINAL) du fichier, plutôt que déduit des lignes. */
  solde_ouverture_fichier: boolean;
  solde_cloture_fichier: boolean;
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
  /** Lignes non retenues et leur raison (jamais importées). */
  lignes_ignorees: LigneIgnoree[];
  /** Le fichier n'a pas de soldes : SIMTIS les calcule (08/10/2026). */
  soldes_calcules: boolean;
  /** Solde d'ouverture proposé pour le calcul ; null : à saisir. */
  solde_ouverture_propose: string | null;
  /** D'où vient la proposition (« Ligne SOLDE INITIAL du fichier », « À saisir »…). */
  solde_ouverture_source: string | null;
  /** Proposition calculée à rebours depuis un solde postérieur au fichier : à vérifier. */
  solde_ouverture_avertissement?: string | null;
  /** Saisie permise : premier import du compte seulement (09/10/2026). */
  solde_ouverture_modifiable?: boolean;
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
  /** « Corrigée » : modifiée dans l'aperçu avant l'enregistrement. */
  origine: "Fichier" | "Corrigée";
  /** Type du Pointage, pour préremplir la fenêtre de modification. */
  pointage_type_id: number | null;
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
  /** Fichier sans soldes : solde d'ouverture du calcul (« 5000000.00 »). */
  soldeOuverture?: string;
};

/** Une ligne du fichier telle que l'aperçu modifiable l'envoie (corrigée ou non). Pas d'ajout. */
export type LigneSoumise = {
  numero: number;
  date_operation: string | null;
  date_valeur: string | null;
  libelle: string | null;
  reference: string | null;
  debit: string | null;
  credit: string | null;
  solde: string | null;
  pointage_type_id: number | null;
  lettrage_escompte: string | null;
  commentaire: string | null;
};

/** Ancien fonctionnement (fichier importé tel quel), ou lignes de l'aperçu modifiable. */
export type ConfirmOptions =
  { garderDoublons: number[]; ecarterErreurs: boolean } | { lignes: LigneSoumise[] };

/** Type d'opération (Pointage) proposé dans les listes de choix. */
export type PointageType = { id: number; code: string; libelle: string };

/** Champs métier d'une opération importée : les seuls modifiables après l'import. */
export type TransactionUpdate = {
  pointage_type_id: number | null;
  lettrage_escompte: string | null;
  commentaire: string | null;
};

/** Ligne du fichier ni importée ni en erreur (titre, total, solde, autre journal…), avec sa raison. */
export type LigneIgnoree = {
  /** Numéro de la ligne dans le fichier Excel. */
  numero: number;
  raison: string;
  cellules: string[];
};
