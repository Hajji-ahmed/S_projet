export type Company = {
  id: number;
  code: string;
  nom: string;
};

export type Currency = {
  code: string;
  libelle: string;
};

/** Vue administrateur : toutes les sociétés, actives ou non (17/11/2026). */
export type CompanyAdmin = Company & { actif: boolean };

export type CompanyCreate = { code: string; nom: string };

/** Le code n'en fait pas partie : il n'est plus modifiable après la création. */
export type CompanyUpdate = { nom?: string; actif?: boolean };
