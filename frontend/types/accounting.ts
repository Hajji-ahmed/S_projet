/** Import Sage et écritures comptables (`backend/app/schemas/accounting.py`). Montants en texte. */
import type { ImportColumn, LigneIgnoree, LineStatus } from "@/types/statement";

export type AccountingFieldCode =
  | "date_ecriture"
  | "journal"
  | "compte"
  | "libelle"
  | "reference"
  | "debit"
  | "credit"
  | "montant"
  | "numero_piece"
  | "echeance"
  | "tiers";

export type AccountingMapping = Partial<Record<AccountingFieldCode, number | null>>;

export type AccountingField = { code: AccountingFieldCode; libelle: string; obligatoire: boolean };

export type LigneComptable = {
  numero: number;
  statut: LineStatus;
  motifs: string[];
  date_ecriture: string | null;
  journal: string | null;
  compte: string | null;
  libelle: string | null;
  reference: string | null;
  debit: string | null;
  credit: string | null;
  montant: string | null;
  numero_piece: string | null;
  echeance: string | null;
  tiers: string | null;
  bank_account_id: number | null;
  bank_code: string | null;
  hash_ligne: string | null;
  /** Doublon interne au fichier : première ligne identique (la ligne peut être gardée). */
  doublon_de: number | null;
  /** Copie d'une ligne de frais SIMTIS (même N° pièce, ligne identique) : décochée par défaut. */
  piece_repetee?: boolean;
};

/** N° pièce d'un frais SIMTIS exporté présent plusieurs fois à l'identique (10/11/2026). */
export type PieceRepetee = {
  numero_piece: string;
  bank_account_id: number;
  bank_code: string | null;
  date_ecriture: string;
  montant: string;
  /** Lignes identiques dans le fichier, la ligne gardée comprise. */
  nb: number;
  /** Numéros des lignes décochées par défaut. */
  copies: number[];
};

export type TotalCompte = {
  bank_account_id: number;
  bank_code: string;
  journal: string;
  nb: number;
  total_debit: string;
  total_credit: string;
  /** Solde comptable avant l'import à la dernière date du fichier (03/11/2026) ; absents dans
   * la réponse de confirmation. `solde_avant` null : pas d'ouverture ou ouverture après le fichier. */
  date_solde?: string | null;
  date_ouverture?: string | null;
  solde_avant?: string | null;
};

export type ResumeComptable = {
  nb_lignes: number;
  nb_valides: number;
  nb_erreurs: number;
  nb_doublons: number;
  nb_ignorees: number;
  total_debit: string;
  total_credit: string;
  periode_debut: string | null;
  periode_fin: string | null;
  par_compte: TotalCompte[];
};

/** Écriture Sage en base qui n'est plus dans le grand livre importé (05/11/2026). */
export type EcritureAbsente = {
  id: number;
  bank_account_id: number;
  bank_code: string;
  journal: string | null;
  compte: string | null;
  date_ecriture: string;
  numero_piece: string | null;
  libelle: string | null;
  debit: string;
  credit: string;
  /** Rapprochement validé qui la contient : à annuler avant de pouvoir la supprimer. */
  code_rapprochement: string | null;
  /** Lignes en erreur sur ce compte dans le fichier : non cochée par défaut. */
  a_verifier: boolean;
};

export type AnalyseComptable = {
  company_id: number;
  fichier_nom: string;
  fichier_hash: string;
  deja_importe: boolean;
  feuilles: string[];
  feuille: string;
  ligne_entete: number;
  colonnes: ImportColumn[];
  champs: AccountingField[];
  mapping: Record<AccountingFieldCode, number | null>;
  mapping_source: "Détection" | "Modèle de la société" | "Utilisateur";
  erreurs_mapping: string[];
  lignes: LigneComptable[];
  /** Lignes non retenues et leur raison (autre journal, contrepartie, titre). */
  lignes_ignorees: LigneIgnoree[];
  resume: ResumeComptable;
  /** Écritures Sage du même compte, journal et période absentes du fichier. */
  ecritures_absentes?: EcritureAbsente[];
  /** Frais SIMTIS exportés présents plusieurs fois à l'identique : double import dans Sage. */
  pieces_repetees?: PieceRepetee[];
};

export type ConfirmationComptable = {
  import_id: number;
  fichier_nom: string;
  nb_importees: number;
  nb_erreurs_ecartees: number;
  nb_doublons_ecartes: number;
  par_compte: TotalCompte[];
  periode_debut: string | null;
  periode_fin: string | null;
  modele_enregistre: boolean;
  /** Écritures absentes du fichier supprimées. */
  nb_supprimees?: number;
};

export type StatutRapprochement = "Non rapprochée" | "À vérifier" | "Rapprochée";

export type Ecriture = {
  id: number;
  /** Compte en devise : colonne « Devise » de Sage, signée comme `montant` (14/10/2026). */
  montant_devise?: string | null;
  /** Devise du compte bancaire ; débit et crédit restent en MAD. */
  devise?: string | null;
  date_ecriture: string;
  journal: string | null;
  compte: string | null;
  libelle: string;
  reference: string | null;
  debit: string;
  credit: string;
  montant: string;
  numero_piece: string | null;
  echeance: string | null;
  tiers: string | null;
  bank_account_id: number | null;
  bank_code: string | null;
  statut: StatutRapprochement;
  /** Code du rapprochement validé de l'écriture (13/10/2026). */
  code_rapprochement?: string | null;
  /** « Sage », « SIMTIS » (frais) ou « Manuelle » (saisie à la main, 24/10/2026). */
  origine?: string;
};

/** Une page de 50 écritures ; total et totaux portent sur tout le filtre. */
export type EcrituresPage = {
  total: number;
  page: number;
  taille: number;
  total_debit: string;
  total_credit: string;
  ecritures: Ecriture[];
};

export type EcritureDetail = Ecriture & {
  fichier_nom: string | null;
  importe_le: string | null;
  importe_par: string | null;
};

export type ImportComptable = {
  id: number;
  importe_le: string;
  importe_par: string | null;
  fichier_nom: string;
  periode_debut: string | null;
  periode_fin: string | null;
  nb_ecritures: number;
  total_debit: string;
  total_credit: string;
  /** « Confirmé » ou « Annulé » (import supprimé, 23/10/2026). */
  statut?: string;
};

/** Solde comptable (Sage) d'un compte à une date (26/10/2026). Débiteur = positif. */
export type SoldeComptable = {
  bank_account_id: number;
  bank_code: string;
  devise: string;
  libelle: string;
  numero: string;
  jour: string;
  date_ouverture: string | null;
  ouverture: string | null;
  debit: string;
  credit: string;
  /** null : solde d'ouverture à saisir. */
  solde: string | null;
  ouverture_devise: string | null;
  solde_devise: string | null;
  solde_bancaire: string | null;
  date_solde_bancaire: string | null;
  /** Solde bancaire − solde comptable, dans la devise du compte. */
  ecart: string | null;
  nb_ecritures: number;
  nb_non_exportees: number;
};
