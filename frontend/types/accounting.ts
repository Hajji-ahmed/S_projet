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
};

export type TotalCompte = {
  bank_account_id: number;
  bank_code: string;
  journal: string;
  nb: number;
  total_debit: string;
  total_credit: string;
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
};

export type StatutRapprochement = "Non rapprochée" | "À vérifier" | "Rapprochée" | "Écart";

export type Ecriture = {
  id: number;
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
};
