/** Rapprochement bancaire 1→1 (P11). Montants et scores en texte exact. */
import type { Ecriture, StatutRapprochement } from "@/types/accounting";

export type StatutCorrespondance = "Proposée" | "Validée" | "Rejetée" | "Annulée";
export type OrigineCorrespondance = "Automatique" | "Manuelle";

export type Critere = {
  code: "reference" | "montant" | "date" | "libelle" | "tiers";
  libelle: string;
  points: string;
};

export type CorrespondanceResume = {
  id: number;
  statut: StatutCorrespondance;
  origine: OrigineCorrespondance;
  score: string | null;
  ecriture_id: number | null;
};

export type Operation = {
  id: number;
  bank_account_id: number;
  bank_code: string;
  date_operation: string;
  date_valeur: string | null;
  libelle: string;
  reference: string | null;
  debit: string;
  credit: string;
  montant: string;
  statut: StatutRapprochement;
  correspondance: CorrespondanceResume | null;
  /** Écart ouvert de l'opération (P12). */
  ecart_id: number | null;
};

/** Une page de 50 opérations ; total et décompte par statut portent sur tout le filtre. */
export type OperationsPage = {
  total: number;
  page: number;
  taille: number;
  par_statut: Record<StatutRapprochement, number>;
  operations: Operation[];
};

export type Correspondance = {
  id: number;
  type: string;
  statut: StatutCorrespondance;
  origine: OrigineCorrespondance;
  score: string | null;
  forte: boolean;
  /** Score du meilleur autre candidat au moment de la proposition (08/10/2026). */
  score_second?: string | null;
  /** Un autre candidat à moins de 10 points : jamais coché d'office. */
  concurrente_proche?: boolean;
  criteres: Critere[];
  commentaire: string | null;
  valide_par: string | null;
  valide_le: string | null;
  /** Dernière décision humaine (validation, rejet, annulation) : historique. */
  decide_par: string | null;
  decide_le: string | null;
  created_at: string;
  operation: Operation;
  ecriture: Ecriture;
};

export type Correspondances = {
  seuil_fort: string;
  correspondances: Correspondance[];
};

export type Candidat = {
  ecriture: Ecriture;
  score: string;
  criteres: Critere[];
  rejetee: boolean;
  proposee_ailleurs: boolean;
};

export type Candidats = {
  operation: Operation;
  seuil_proposition: string;
  seuil_fort: string;
  candidats: Candidat[];
};

export type RunResult = {
  nb_operations: number;
  nb_ecritures: number;
  nb_propositions: number;
  nb_fortes: number;
  nb_operations_ambigues: number;
  nb_ecritures_ambigues: number;
};

export type StatutDecision = "Validée" | "Rejetée" | "Annulée";

/** Une page de 50 décisions ; `par_statut` porte sur tout le filtre, hors statut. */
export type Historique = {
  total: number;
  page: number;
  taille: number;
  par_statut: Record<StatutDecision, number>;
  decisions: Correspondance[];
};

/** Opération ambiguë : plusieurs écritures aussi proches, aucune proposée par le moteur. */
export type Ambigue = {
  operation: Operation;
  candidats: Candidat[];
};

export type Ambigues = {
  /** Nombre d'opérations ambiguës sur tout le filtre ; `ambigues` n'en donne qu'une page. */
  total: number;
  page: number;
  taille: number;
  seuil_fort: string;
  ambigues: Ambigue[];
};
