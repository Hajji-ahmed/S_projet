/** Tableau Banques calculé (`backend/app/schemas/position.py`). Montants en texte exact. */

export type BanqueColonne = {
  bank_id: number;
  code: string;
  logo: string | null;
  /** Compte courant MAD actif de la banque ; `null` sans compte (toute la colonne vaut « - »). */
  bank_account_id: number | null;
  taux_pct: string | null;
  ligne: string | null;
};

export type CelluleBanque = {
  bank_id: number;
  valeur: string | null;
  /** Date du solde utilisé ; `reprise` quand ce n'est pas le jour de la ligne. */
  date_solde: string | null;
  reprise: boolean;
};

export type LigneBanques = {
  cellules: CelluleBanque[];
  total: string | null;
  depassement: string | null;
};

export type JourBanques = LigneBanques & { date: string };

/** Lignes EUR et USD du tableau Devises : soldes des comptes en devise, jamais convertis. */
export type DevisesSoldes = {
  company_id: number;
  date_fin: string;
  /** Faux : la société n'a aucun compte en devise ni DH convertible, pas de tableau Devises. */
  affiche: boolean;
  banques: { bank_id: number; code: string; logo: string | null }[];
  lignes: { devise: "EUR" | "USD"; cellules: CelluleBanque[]; total: string | null }[];
};

export type BanquesTable = {
  company_id: number;
  date_fin: string;
  banques: BanqueColonne[];
  ligne_total: string | null;
  /** Du plus ancien au plus récent ; la date de fin en dernier. */
  jours: JourBanques[];
  disponible: LigneBanques;
};
