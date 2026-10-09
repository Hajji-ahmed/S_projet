/** Chiffres d'un compte à aujourd'hui. Montants en texte exact ; null = inconnu (jamais saisi). */
export type Figures = {
  solde: string | null;
  credit_utilise: string | null;
  credit_disponible: string | null;
  position_disponible: string | null;
  /** Date de la dernière saisie, « AAAA-MM-JJ ». */
  date_maj: string | null;
  /** Solde = solde de clôture du relevé importé : il ne se saisit pas (08/10/2026). */
  solde_releve?: boolean;
};

export type Balance = {
  id: number;
  date_solde: string;
  solde: string | null;
  credit_utilise: string | null;
  source: "Saisie" | "Relevé";
  commentaire: string | null;
  saisi_par: string | null;
};

export type BalanceInput = {
  solde: string | null;
  credit_utilise: string | null;
  commentaire: string | null;
};
