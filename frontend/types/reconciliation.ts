/** Rapprochement bancaire 1→1 (P11). Montants et scores en texte exact. */
import type { Ecriture, StatutRapprochement } from "@/types/accounting";

export type StatutCorrespondance = "Proposée" | "Validée" | "Rejetée" | "Annulée";
/** « Frais » : droits de timbre comptabilisés par SIMTIS (13/10/2026). */
export type OrigineCorrespondance = "Automatique" | "Manuelle" | "Frais";

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
  /** Code du rapprochement validé (« BP-26-000123 », 13/10/2026). */
  code?: string | null;
};

export type Operation = {
  id: number;
  bank_account_id: number;
  bank_code: string;
  /** Devise du compte : le montant est dans cette devise (14/10/2026). */
  devise?: string;
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
  /** Libellé terminé par « (*) » : en cours, jamais rapprochée (20/10/2026). */
  en_cours?: boolean;
};

/** Une page de 50 opérations ; total et décompte par statut portent sur tout le filtre. */
export type OperationsPage = {
  total: number;
  page: number;
  taille: number;
  par_statut: Record<StatutRapprochement, number>;
  /** Frais bancaires non rapprochés, à passer dans Sage (hors « Non rapprochée », 12/10/2026). */
  a_comptabiliser?: number;
  total_a_comptabiliser?: string;
  /** Opérations en cours du filtre, hors décompte par statut (20/10/2026). */
  en_cours?: number;
  operations: Operation[];
};

export type Correspondance = {
  id: number;
  /** Code donné à la validation (« BP-26-000123 ») ; null tant que proposée. */
  code?: string | null;
  type: string;
  statut: StatutCorrespondance;
  origine: OrigineCorrespondance;
  score: string | null;
  forte: boolean;
  /** Score du meilleur autre candidat au moment de la proposition (08/10/2026). */
  score_second?: string | null;
  /** Un autre candidat à moins de 10 points : jamais coché d'office. */
  concurrente_proche?: boolean;
  /** Recherche élargie (20/10/2026) : écart entre les dates ; jamais cochée d'office. */
  elargie?: boolean;
  ecart_jours?: number | null;
  criteres: Critere[];
  commentaire: string | null;
  valide_par: string | null;
  valide_le: string | null;
  /** Dernière décision humaine (validation, rejet, annulation) : historique. */
  decide_par: string | null;
  decide_le: string | null;
  created_at: string;
  /** Opération principale (la seule en 1 → 1, la plus grosse d'un groupe). */
  operation: Operation;
  /** Groupe N → 1 (12/10/2026) : toutes les opérations, leur total et l'écart avec l'écriture. */
  operations?: Operation[];
  total_operations?: string;
  ecart?: string;
  explication?: string | null;
  ecriture: Ecriture;
  /** Toutes les écritures (1 → N, N → N, P13 du 15/10/2026), la plus grosse en tête. */
  ecritures?: Ecriture[];
  total_ecritures?: string;
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
  /** Groupes N → 1 proposés (12/10/2026). */
  nb_groupes?: number;
  nb_ecritures_ambigues: number;
};

/** Résultat de la recherche élargie (20/10/2026). */
export type RunElargiResult = {
  nb_operations: number;
  nb_ecritures: number;
  nb_propositions: number;
  fenetre_jours: number;
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

/** Écriture ambiguë (15/10/2026) : ses opérations candidates, la meilleure d'abord. */
export type CandidatOperation = {
  operation: Operation;
  score: string;
  criteres: Critere[];
  rejetee: boolean;
  proposee_ailleurs: boolean;
};

export type EcritureAmbigue = {
  ecriture: Ecriture;
  candidats: CandidatOperation[];
};

export type EcrituresAmbigues = {
  /** Nombre d'écritures ambiguës sur tout le filtre ; `ecritures` n'en donne qu'une page. */
  total: number;
  page: number;
  taille: number;
  ecritures: EcritureAmbigue[];
};

export type Ambigues = {
  /** Nombre d'opérations ambiguës sur tout le filtre ; `ambigues` n'en donne qu'une page. */
  total: number;
  page: number;
  taille: number;
  seuil_fort: string;
  ambigues: Ambigue[];
};
