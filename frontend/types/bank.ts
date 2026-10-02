import type { Figures } from "@/types/balance";

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
  /** Compte courant MAD de la société active (null sans société indiquée ou sans ce compte). */
  figures: Figures | null;
  /** Autres comptes de la société active, chacun dans sa devise (jamais additionnés). */
  autres_comptes: OtherAccount[];
};

export type OtherAccount = {
  devise: string;
  type_compte: "Courant" | "DH convertible";
  solde: string | null;
  date_maj: string | null;
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
