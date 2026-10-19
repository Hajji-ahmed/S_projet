/** Dashboard (P15, 14/10/2026). Montants en texte exact ("12500.50"), jamais en float. */

export type Kpi = {
  valeur: string | null;
  /** Variation en % par rapport à la période précédente de même durée (« 2.5 », « -10.0 »). */
  variation: string | null;
};

export type CompteDashboard = {
  id: number;
  bank_id: number;
  bank_code: string;
  bank_nom: string;
  bank_logo: string | null;
  numero: string;
  devise: string;
  solde: string | null;
  variation: string | null;
  /** LIGNE d'un compte courant MAD ; null pour un compte en devise. */
  ligne: string | null;
  /** Solde + LIGNE (compte courant MAD) ; null sinon. */
  disponible: string | null;
};

export type FluxJour = { date: string; encaissements: string; decaissements: string };

export type OperationDashboard = {
  id: number;
  date_operation: string;
  bank_code: string;
  devise: string;
  libelle: string;
  debit: string;
  credit: string;
  statut: string;
};

export type Alerte = {
  niveau: "danger" | "warning" | "info";
  message: string;
  lien: string;
};

/** Travail en attente de la période (onglet « Suivi », 19/10/2026). */
export type Taches = {
  propositions_fortes: number;
  propositions_a_verifier: number;
  operations_ambigues: number;
  ecritures_ambigues: number;
  a_comptabiliser: number;
  a_exporter: number;
};

/** Avancement du rapprochement et frais d'une banque sur la période. */
export type BanqueDashboard = {
  code: string;
  logo: string | null;
  rapprochees: number;
  a_rapprocher: number;
  total: number;
  frais: string;
};

export type Dashboard = {
  date_from: string;
  date_to: string;
  /** Banque filtrée ; null = toutes (19/10/2026). */
  bank_id: number | null;
  /** Banques de la société (liste du filtre). */
  banques_societe: { id: number; code: string; logo: string | null }[];
  taches: Taches;
  banques: BanqueDashboard[];
  solde_total: Kpi;
  /** Somme des LIGNES des comptes courants MAD. */
  ligne_totale: string;
  /** Solde total + LIGNE totale ; null sans solde connu. */
  disponible: string | null;
  encaissements: Kpi;
  decaissements: Kpi;
  rapprochees: number;
  a_rapprocher: number;
  total_operations: number;
  evolution: { date: string; solde: string | null }[];
  /** Encaissements et décaissements de chaque jour de la période (0 un jour sans mouvement). */
  flux: FluxJour[];
  a_comptabiliser: number;
  frais: { code: string; libelle: string; total: string }[];
  frais_total: string;
  comptes: CompteDashboard[];
  dernieres_operations: OperationDashboard[];
  ecritures_exportees: number;
  ecritures_a_exporter: number;
  alertes: Alerte[];
};
