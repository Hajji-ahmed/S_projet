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

export type LignePrevisions = {
  /** Date de la ligne (décision du 30/10/2026). */
  jour: string;
  /** Rang de la ligne parmi celles de sa date, donné par le serveur. */
  ligne: number;
  libelle: string | null;
  banques: MontantBanque[];
  /** Montants sans banque de la ligne (une valeur par ligne depuis le 03/10/2026). */
  encaissement: string | null;
  escompte: string | null;
  douane: string | null;
};

export type Previsions = { company_id: number; jour: string; lignes: LignePrevisions[] };

/** Les lignes à partir de la date de la page ; leur rang est donné par le serveur. */
export type PrevisionsInput = { lignes: Omit<LignePrevisions, "ligne">[] };
