/**
 * Saisie du solde du jour : mêmes règles que `backend/app/schemas/balance.py` et `balance_service.py`.
 * Les montants restent en texte (aucune virgule flottante) ; les dates en « AAAA-MM-JJ ».
 */
import { normalizeAmountInput } from "@/lib/accounts";

const BUSINESS_TIME_ZONE = "Africa/Casablanca";

/** Date du jour au Maroc, « AAAA-MM-JJ » (la date du serveur ou du poste peut différer). */
export function businessToday(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: BUSINESS_TIME_ZONE }).format(now);
}

/** « 2026-09-30 » → « 30/09/2026 » ; absent → « - ». Sans objet Date : aucun décalage de fuseau. */
export function formatDate(iso: string | null): string {
  if (!iso) return "-";
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year}`;
}

/** Symbole affiché après un montant : « DH » pour le dirham, sinon le code de la devise. */
export function currencySuffix(devise: string): string {
  return devise === "MAD" ? "DH" : devise;
}

/** Comme `normalizeAmountInput`, mais un solde peut être négatif (découvert). */
export function normalizeSignedAmountInput(text: string): string | null {
  const trimmed = text.trim();
  const negative = trimmed.startsWith("-");
  const amount = normalizeAmountInput(negative ? trimmed.slice(1) : trimmed);
  return amount === null ? null : `${negative ? "-" : ""}${amount}`;
}

export type BalanceFormValues = {
  jour: string;
  solde: string;
  credit_utilise: string;
  commentaire: string;
};

export type BalanceFormErrors = Partial<Record<keyof BalanceFormValues | "global", string>>;

export function validateBalanceForm(values: BalanceFormValues, today: string): BalanceFormErrors {
  const errors: BalanceFormErrors = {};

  if (!/^\d{4}-\d{2}-\d{2}$/.test(values.jour)) {
    errors.jour = "Choisissez une date.";
  } else if (values.jour > today) {
    errors.jour = "Impossible de saisir un solde pour une date future.";
  }

  const solde = values.solde.trim();
  const utilise = values.credit_utilise.trim();
  if (!solde && !utilise) {
    errors.global = "Saisissez le solde, le crédit utilisé, ou les deux.";
  }
  if (solde && normalizeSignedAmountInput(solde) === null) {
    errors.solde = "Un montant, 2 décimales au plus (ex. 1 200 000 ou -15 000,50).";
  }
  if (utilise && normalizeAmountInput(utilise) === null) {
    errors.credit_utilise = "Un montant positif, 2 décimales au plus.";
  }
  if (values.commentaire.length > 500) {
    errors.commentaire = "500 caractères au plus.";
  }
  return errors;
}
