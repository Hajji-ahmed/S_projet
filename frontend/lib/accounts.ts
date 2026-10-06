/**
 * Saisie des comptes : validation (mêmes règles que `backend/app/schemas/account.py`) et conversion
 * des montants et des taux saisis. Tout reste en TEXTE : aucun calcul à virgule flottante, l'API
 * reçoit exactement ce que l'utilisateur a tapé (« 500 000,50 » → « 500000.50 »).
 */
import { formatAmount } from "@/lib/format";
import type { TypeCompte } from "@/types/account";

export const TYPE_COMPTE_OPTIONS: readonly { value: TypeCompte; label: string }[] = [
  { value: "Courant", label: "Courant" },
  { value: "DH convertible", label: "DH convertible" },
];

export type AccountFormValues = {
  bank_id: string;
  devise: string;
  type_compte: TypeCompte;
  libelle: string;
  numero: string;
  compte_comptable: string;
  /** Journal de banque Sage (ex. BQ1), tel que saisi (vide = aucun). */
  journal_sage: string;
  /** LIGNE (crédit autorisé), telle que saisie. */
  credit_autorise: string;
  /** Taux en %, tel que saisi (vide = aucun). */
  taux: string;
};

export type AccountFormErrors = Partial<Record<keyof AccountFormValues, string>>;

/** Espaces normaux, insécables et fines (copier-coller depuis Excel) supprimés, virgule → point. */
function cleanNumber(text: string): string {
  return text.replace(/[\s  ]/g, "").replace(",", ".");
}

/** « 500 000,50 » → « 500000.50 ». Null si ce n'est pas un montant positif à 2 décimales au plus. */
export function normalizeAmountInput(text: string): string | null {
  const value = cleanNumber(text);
  return /^\d{1,16}(\.\d{1,2})?$/.test(value) ? value : null;
}

/** « 4,5 » → « 4.5 ». Null si ce n'est pas un pourcentage entre 0 et 100, 4 décimales au plus. */
export function normalizePercentInput(text: string): string | null {
  const value = cleanNumber(text);
  const match = /^(\d{1,3})(?:\.(\d{1,4}))?$/.exec(value);
  if (!match) return null;
  const whole = Number(match[1]); // entier de 0 à 999 : aucune perte de précision
  const decimals = match[2] ?? "";
  if (whole > 100 || (whole === 100 && /[1-9]/.test(decimals))) return null;
  return value;
}

export function normalizeNumero(text: string): string {
  return text.replace(/\s/g, "").toUpperCase();
}

/** Valeur de l'API (« 500000.00 ») vers le champ de saisie (« 500 000 »). */
export function amountForInput(value: string): string {
  return formatAmount(value);
}

/** « 4.5 » → « 4,5 % » ; aucun taux → « - ». */
export function formatPercent(value: string | null): string {
  return value === null ? "-" : `${value.replace(".", ",")} %`;
}

export function validateAccountForm(
  values: AccountFormValues,
  mode: "create" | "edit",
): AccountFormErrors {
  const errors: AccountFormErrors = {};

  if (mode === "create" && !values.bank_id) errors.bank_id = "Choisissez une banque.";
  if (mode === "create" && !values.devise) errors.devise = "Choisissez une devise.";
  if (values.type_compte === "DH convertible" && values.devise !== "MAD") {
    errors.type_compte = "Un compte DH convertible doit être en MAD.";
  }

  const libelle = values.libelle.trim();
  if (libelle.length < 2 || libelle.length > 120) {
    errors.libelle = "Le libellé doit contenir entre 2 et 120 caractères.";
  }
  if (!/^[A-Z0-9-]{5,40}$/.test(normalizeNumero(values.numero))) {
    errors.numero = "5 à 40 lettres, chiffres ou tirets (les espaces sont ignorés).";
  }
  const compte = values.compte_comptable.trim().toUpperCase();
  if (compte && !/^[A-Z0-9]{1,20}$/.test(compte)) {
    errors.compte_comptable = "1 à 20 lettres ou chiffres (ex. 5141).";
  }
  const journal = values.journal_sage.trim().toUpperCase();
  if (journal && !/^[A-Z0-9]{1,10}$/.test(journal)) {
    errors.journal_sage = "1 à 10 lettres ou chiffres (ex. BQ1).";
  }
  if (normalizeAmountInput(values.credit_autorise) === null) {
    errors.credit_autorise = "Un montant positif, 2 décimales au plus (ex. 500 000).";
  }
  if (values.taux.trim() && normalizePercentInput(values.taux) === null) {
    errors.taux = "Un pourcentage entre 0 et 100 (ex. 4,5).";
  }
  return errors;
}
