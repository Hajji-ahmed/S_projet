/** Tableaux Devises et Prévisions saisis à la main (`backend/app/schemas/saisie.py`). */

export type LigneDevise = "EUR" | "USD" | "Exp DH convertible";

/** Montant d'une cellule de banque, en texte exact (« 1250.50 »). */
export type MontantBanque = { bank_id: number; montant: string };

export type LigneDevises = {
  ligne: LigneDevise;
  banques: MontantBanque[];
  total: string | null;
  depassement: string | null;
};

export type Devises = { company_id: number; jour: string; lignes: LigneDevises[] };

export type DevisesInput = { lignes: LigneDevises[] };

export type LignePrevisions = { ligne: number; libelle: string | null; banques: MontantBanque[] };

export type Previsions = {
  company_id: number;
  jour: string;
  lignes: LignePrevisions[];
  /** Les trois cellules fusionnées de la journée, sans banque. */
  encaissement: string | null;
  escompte: string | null;
  douane: string | null;
};

export type PrevisionsInput = Omit<Previsions, "company_id" | "jour">;
