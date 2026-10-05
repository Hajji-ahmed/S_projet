"use client";

import { useEffect, useState } from "react";

import { DateInput, Field, NumberInput, TextInput } from "@/components/ui/Field";
import { FormModal } from "@/components/ui/FormModal";
import { amountForInput, normalizeAmountInput } from "@/lib/accounts";
import { ApiError } from "@/lib/api";
import {
  PREMIERE_DATE_SOLDE,
  businessToday,
  currencySuffix,
  formatDate,
  normalizeSignedAmountInput,
  validateBalanceForm,
  type BalanceFormErrors,
  type BalanceFormValues,
} from "@/lib/balances";
import { listBalances, saveBalance } from "@/services/balances";
import type { Balance } from "@/types/balance";

export type BalanceTarget = {
  id: number;
  bank_code: string;
  devise: string;
  libelle: string;
};

type BalanceFormModalProps = {
  account: BalanceTarget;
  onClose: () => void;
  onSaved: (balance: Balance) => void;
};

/**
 * Saisie du solde et du crédit utilisé d'un jour. Si ce jour a déjà une saisie, elle est préremplie :
 * l'enregistrement la remplace (sans préremplissage, un champ laissé vide effacerait l'ancienne valeur).
 */
export function BalanceFormModal({ account, onClose, onSaved }: BalanceFormModalProps) {
  const today = businessToday();
  const [values, setValues] = useState<BalanceFormValues>({
    jour: today,
    solde: "",
    credit_utilise: "",
    commentaire: "",
  });
  const [existing, setExisting] = useState<Balance | null>(null);
  const [errors, setErrors] = useState<BalanceFormErrors>({});
  const [apiError, setApiError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const suffix = currencySuffix(account.devise);

  // Préremplissage avec la saisie existante du jour choisi
  useEffect(() => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(values.jour)) return;
    let cancelled = false;
    listBalances(account.id, values.jour, values.jour).then(
      ([found]) => {
        if (cancelled) return;
        setExisting(found ?? null);
        setValues((current) => ({
          ...current,
          solde: found?.solde ? amountForInput(found.solde) : "",
          credit_utilise: found?.credit_utilise ? amountForInput(found.credit_utilise) : "",
          commentaire: found?.commentaire ?? "",
        }));
      },
      () => undefined, // sans préremplissage, la saisie reste possible
    );
    return () => {
      cancelled = true;
    };
  }, [account.id, values.jour]);

  const set = (field: keyof BalanceFormValues) => (value: string) =>
    setValues((current) => ({ ...current, [field]: value }));

  async function handleSubmit() {
    const found = validateBalanceForm(values, today);
    setErrors(found);
    setApiError(found.global ?? null);
    if (Object.keys(found).length > 0) return;

    setSubmitting(true);
    try {
      const saved = await saveBalance(account.id, values.jour, {
        solde: values.solde.trim() ? normalizeSignedAmountInput(values.solde) : null,
        credit_utilise: values.credit_utilise.trim()
          ? normalizeAmountInput(values.credit_utilise)
          : null,
        commentaire: values.commentaire.trim() || null,
      });
      onSaved(saved);
    } catch (error) {
      setApiError(
        error instanceof ApiError && error.status !== 422
          ? error.message
          : "Enregistrement impossible. Vérifiez les champs puis réessayez.",
      );
      setSubmitting(false);
    }
  }

  return (
    <FormModal
      open
      title={`Solde du compte ${account.bank_code} ${account.devise}`}
      onClose={onClose}
      onSubmit={handleSubmit}
      submitting={submitting}
      error={apiError}
    >
      <p className="-mt-1 text-sm text-simtis-muted">{account.libelle}</p>

      <Field
        label="Date"
        htmlFor="balance-jour"
        required
        error={errors.jour}
        hint={
          existing
            ? `Une saisie existe déjà pour le ${formatDate(existing.date_solde)} : elle sera corrigée.`
            : "Aujourd'hui par défaut ; un jour passé peut être saisi ou corrigé."
        }
      >
        <DateInput
          id="balance-jour"
          value={values.jour}
          min={PREMIERE_DATE_SOLDE}
          max={today}
          onChange={(event) => set("jour")(event.target.value)}
          disabled={submitting}
          invalid={!!errors.jour}
          className="max-w-[200px]"
        />
      </Field>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label={`Solde (${suffix})`}
          htmlFor="balance-solde"
          error={errors.solde}
          hint="Négatif en cas de découvert."
        >
          <NumberInput
            id="balance-solde"
            value={values.solde}
            onChange={(event) => set("solde")(event.target.value)}
            disabled={submitting}
            inputMode="decimal"
            autoFocus
            invalid={!!errors.solde}
          />
        </Field>
        <Field
          label={`Crédit utilisé (${suffix})`}
          htmlFor="balance-utilise"
          error={errors.credit_utilise}
          hint="Part de la LIGNE utilisée."
        >
          <NumberInput
            id="balance-utilise"
            value={values.credit_utilise}
            onChange={(event) => set("credit_utilise")(event.target.value)}
            disabled={submitting}
            inputMode="decimal"
            invalid={!!errors.credit_utilise}
          />
        </Field>
      </div>

      <Field label="Commentaire" htmlFor="balance-commentaire" error={errors.commentaire}>
        <TextInput
          id="balance-commentaire"
          value={values.commentaire}
          onChange={(event) => set("commentaire")(event.target.value)}
          disabled={submitting}
          maxLength={500}
          invalid={!!errors.commentaire}
        />
      </Field>
    </FormModal>
  );
}
