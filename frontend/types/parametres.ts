/** Paramètres (P16.3) : grille de rapprochement et modèles de mapping d'import. */

export type Regle = {
  id: number;
  code: string;
  libelle: string;
  /** critere : points + actif (DATE : + jours) ; seuil : points ; fenetre : jours. */
  genre: "critere" | "seuil" | "fenetre" | "autre";
  poids: string;
  tolerance: string | null;
  actif: boolean;
  updated_at: string;
};

export type RegleInput = {
  code: string;
  poids: string;
  tolerance: string | null;
  actif: boolean;
};

export type ModeleMapping = {
  id: number;
  type: string;
  nom: string;
  banque: string | null;
  company_id: number | null;
  /** Champ standard → colonne du fichier. */
  mapping: Record<string, unknown>;
  updated_at: string;
};
