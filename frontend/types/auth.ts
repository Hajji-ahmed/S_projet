export type CurrentUser = {
  id: number;
  nom: string;
  email: string;
  /** Noms des rôles, ex. « Trésorerie ». */
  roles: string[];
  /** Codes de permission effectifs, ex. « banks.manage ». */
  permissions: string[];
  /** Sociétés accessibles (19/11/2026) ; null = toutes. */
  societes?: number[] | null;
};

export type TokenResponse = {
  access_token: string;
  token_type: "bearer";
  /** Durée de validité du jeton d'accès, en secondes. */
  expires_in: number;
  user: CurrentUser;
};
