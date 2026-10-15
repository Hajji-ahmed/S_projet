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

export type Dashboard = {
  date_from: string;
  date_to: string;
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
