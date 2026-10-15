/** Historique (P16.2) : le journal d'audit, en lecture seule. */

export type LigneHistorique = {
  id: number;
  created_at: string;
  user_id: number | null;
  /** null : action système (commande en ligne, migration, tentative anonyme). */
  utilisateur: string | null;
  action: string;
  action_libelle: string;
  entite: string;
  entite_libelle: string;
  entite_id: string | null;
  resume: string;
  ip: string | null;
};

export type PageHistorique = {
  items: LigneHistorique[];
  total: number;
  page: number;
  pages: number;
};

/** Valeurs JSON telles qu'enregistrées (montants en texte exact). */
export type ValeurJson =
  string | number | boolean | null | ValeurJson[] | { [cle: string]: ValeurJson };

export type Difference = {
  champ: string;
  avant: ValeurJson;
  apres: ValeurJson;
  modifie: boolean;
};

export type DetailHistorique = LigneHistorique & {
  avant: Record<string, ValeurJson> | null;
  apres: Record<string, ValeurJson> | null;
  differences: Difference[];
};

export type FiltresHistorique = {
  actions: { code: string; libelle: string; nb: number | null }[];
  entites: { code: string; libelle: string; nb: number | null }[];
  utilisateurs: { id: number; nom: string }[];
};

export type RechercheHistorique = {
  page: number;
  user_id: string;
  action: string;
  entite: string;
  from: string;
  to: string;
};
