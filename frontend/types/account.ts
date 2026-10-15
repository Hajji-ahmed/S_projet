import type { Figures } from "@/types/balance";

export type TypeCompte = "Courant" | "DH convertible";

export type Account = {
  id: number;
  company_id: number;
  bank_id: number;
  bank_code: string;
  bank_nom: string;
  bank_logo: string | null;
  libelle: string;
  numero: string;
  devise: string;
  type_compte: TypeCompte;
  compte_comptable: string | null;
  /** Code du journal de banque dans Sage (ex. BQ1) : rattache les écritures importées (P10). */
  journal_sage: string | null;
  /** Journal Sage des frais bancaires (ex. 5543) ; à défaut, le seul journal du compte (13/10/2026). */
  journal_frais?: string | null;
  /** Compte de charge des droits de timbre, pour l'export vers Sage (13/10/2026). */
  compte_timbre?: string | null;
  /** Comptes Sage de l'export des commissions (13/10/2026). */
  compte_commission?: string | null;
  compte_commission_effet?: string | null;
  compte_tva?: string | null;
  /** LIGNE (crédit autorisé), en texte exact : "500000.00". */
  credit_autorise: string;
  /** Taux d'intérêt en pourcentage, en texte : "4.5" = 4,5 %. */
  taux_interet_pct: string | null;
  actif: boolean;
  /** Relevés, opérations, écritures, imports ou contrôles : le compte ne peut alors être que
   * désactivé, jamais supprimé. */
  a_historique: boolean;
  /** Chiffres à aujourd'hui (solde, crédit et position disponibles). */
  figures: Figures | null;
};

export type AccountFilters = {
  bank_id?: number;
  devise?: string;
  actif?: boolean;
};

export type AccountUpdate = {
  libelle: string;
  numero: string;
  type_compte: TypeCompte;
  compte_comptable: string | null;
  journal_sage: string | null;
  journal_frais: string | null;
  compte_timbre: string | null;
  compte_commission: string | null;
  compte_commission_effet: string | null;
  compte_tva: string | null;
  credit_autorise: string;
  taux_interet_pct: string | null;
};

export type AccountCreate = AccountUpdate & {
  company_id: number;
  bank_id: number;
  devise: string;
};
