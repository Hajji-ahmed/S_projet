/** Écarts (P12). Montants en texte exact. */

export const TYPES_ECART = [
  "Banque sans écriture",
  "Écriture sans banque",
  "Montant différent",
  "Date différente",
  "Libellé ambigu",
  "Doublon potentiel",
] as const;
export type TypeEcart = (typeof TYPES_ECART)[number];

export const STATUTS_ECART = ["À traiter", "En cours", "Traité", "Clôturé"] as const;
export type StatutEcart = (typeof STATUTS_ECART)[number];

export type OperationEcart = {
  id: number;
  date_operation: string;
  libelle: string;
  reference: string | null;
  debit: string;
  credit: string;
  montant: string;
  statut: string;
};

export type EcritureEcart = {
  id: number;
  date_ecriture: string;
  journal: string | null;
  libelle: string;
  numero_piece: string | null;
  tiers: string | null;
  debit: string;
  credit: string;
  montant: string;
  echeance: string | null;
  statut: string;
};

export type Ecart = {
  id: number;
  type: TypeEcart;
  statut: StatutEcart;
  date_ecart: string;
  montant: string;
  difference: string | null;
  devise: string | null;
  bank_code: string | null;
  libelle: string | null;
  responsable_id: number | null;
  responsable: string | null;
  commentaire: string | null;
  traite_le: string | null;
  cloture_le: string | null;
  created_at: string;
  operation: OperationEcart | null;
  ecriture: EcritureEcart | null;
};

export type Evenement = {
  action: string;
  auteur: string | null;
  le: string;
  avant: Record<string, unknown> | null;
  apres: Record<string, unknown> | null;
};

export type EcartDetail = Ecart & {
  cloture_par: string | null;
  historique: Evenement[];
};

/** Une page de 50 écarts ; compteurs et montants portent sur tout le filtre. */
export type EcartsPage = {
  total: number;
  page: number;
  taille: number;
  par_statut: Record<StatutEcart, number>;
  /** Montant des écarts ouverts par devise : jamais additionné entre devises. */
  montants_ouverts: Record<string, string>;
  ecarts: Ecart[];
};

export type EcartCreate = {
  type: TypeEcart;
  transaction_id?: number | null;
  ecriture_id?: number | null;
  commentaire?: string | null;
  responsable_id?: number | null;
};

export type EcartUpdate = {
  statut?: "À traiter" | "En cours" | "Traité";
  responsable_id?: number | null;
  commentaire?: string | null;
};

export type GenerationEcarts = {
  banque_sans_ecriture: number;
  ecriture_sans_banque: number;
  doublons: number;
  total: number;
  date_limite: string;
};

export type Responsable = { id: number; nom: string };
