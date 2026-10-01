export type Bank = {
  id: number;
  /** Code affiché dans les colonnes des tableaux (AWB, BMCE...). Non modifiable après création. */
  code: string;
  nom: string;
  /** Chemin d'un fichier de `public/banques/`, ou null. */
  logo: string | null;
  ordre_affichage: number;
  actif: boolean;
  nb_comptes_actifs: number;
};

export type BankCreate = {
  code: string;
  nom: string;
  logo: string | null;
  ordre_affichage: number | null;
};

export type BankUpdate = {
  nom: string;
  logo: string | null;
  ordre_affichage: number;
};
