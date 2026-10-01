"use client";

import { useState } from "react";

import { Field, NumberInput, Select, TextInput } from "@/components/ui/Field";
import { FormModal } from "@/components/ui/FormModal";
import {
  TYPE_COMPTE_OPTIONS,
  amountForInput,
  normalizeAmountInput,
  normalizeNumero,
  normalizePercentInput,
  validateAccountForm,
  type AccountFormErrors,
  type AccountFormValues,
} from "@/lib/accounts";
import { ApiError } from "@/lib/api";
import { createAccount, updateAccount } from "@/services/accounts";
import type { Account, TypeCompte } from "@/types/account";
import type { Bank } from "@/types/bank";
import type { Company, Currency } from "@/types/company";

type AccountFormModalProps = {
  /** Compte à modifier ; absent = création dans la société active. */
  account?: Account;
  company: Company;
  banks: Bank[];
  currencies: Currency[];
  onClose: () => void;
  onSaved: (account: Account, mode: "create" | "edit") => void;
};

function initialValues(account?: Account): AccountFormValues {
  if (!account) {
    return {
      bank_id: "",
      devise: "MAD",
      type_compte: "Courant",
      libelle: "",
      numero: "",
      compte_comptable: "",
      credit_autorise: "0",
      taux: "",
    };
  }
  return {
    bank_id: String(account.bank_id),
    devise: account.devise,
    type_compte: account.type_compte,
    libelle: account.libelle,
    numero: account.numero,
    compte_comptable: account.compte_comptable ?? "",
    credit_autorise: amountForInput(account.credit_autorise),
    taux: account.taux_interet_pct?.replace(".", ",") ?? "",
  };
}

/** À monter seulement quand la fenêtre est ouverte : son état repart de zéro à chaque ouverture. */
export function AccountFormModal({
  account,
  company,
  banks,
  currencies,
  onClose,
  onSaved,
}: AccountFormModalProps) {
  const mode = account ? "edit" : "create";
  const [values, setValues] = useState<AccountFormValues>(() => initialValues(account));
  const [errors, setErrors] = useState<AccountFormErrors>({});
  const [apiError, setApiError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const set = (field: keyof AccountFormValues) => (value: string) =>
    setValues((current) => ({ ...current, [field]: value }));

  // Création : seules les banques actives peuvent recevoir un compte. Modification : la banque du
  // compte reste affichée même si elle a été désactivée depuis.
  const bankOptions = banks
    .filter((bank) => bank.actif || String(bank.id) === values.bank_id)
    .map((bank) => ({ value: String(bank.id), label: `${bank.code} — ${bank.nom}` }));
  const currencyOptions = currencies.map((currency) => ({
    value: currency.code,
    label: `${currency.code} — ${currency.libelle}`,
  }));
  const deviseSuffix = values.devise === "MAD" ? "DH" : values.devise;

  function changeType(type: TypeCompte) {
    // Un compte DH convertible est toujours en MAD : la devise suit à la création
    setValues((current) => ({
      ...current,
      type_compte: type,
      devise: type === "DH convertible" && mode === "create" ? "MAD" : current.devise,
    }));
  }

  async function handleSubmit() {
    const found = validateAccountForm(values, mode);
    setErrors(found);
    setApiError(null);
    if (Object.keys(found).length > 0) return;

    setSubmitting(true);
    const common = {
      libelle: values.libelle.trim(),
      numero: normalizeNumero(values.numero),
      type_compte: values.type_compte,
      compte_comptable: values.compte_comptable.trim().toUpperCase() || null,
      credit_autorise: normalizeAmountInput(values.credit_autorise) as string,
      taux_interet_pct: values.taux.trim() ? normalizePercentInput(values.taux) : null,
    };
    try {
      const saved = account
        ? await updateAccount(account.id, common)
        : await createAccount({
            ...common,
            company_id: company.id,
            bank_id: Number(values.bank_id),
            devise: values.devise,
          });
      onSaved(saved, mode);
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
      title={
        account ? `Modifier le compte ${account.bank_code} ${account.devise}` : "Nouveau compte"
      }
      onClose={onClose}
      onSubmit={handleSubmit}
      submitting={submitting}
      error={apiError}
    >
      <Field
        label="Société"
        htmlFor="account-societe"
        hint={mode === "create" ? "Société active, choisie dans l'en-tête." : undefined}
      >
        <TextInput id="account-societe" value={company.nom} disabled readOnly />
      </Field>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="Banque"
          htmlFor="account-bank"
          required={mode === "create"}
          error={errors.bank_id}
        >
          <Select
            id="account-bank"
            value={values.bank_id}
            onChange={(event) => set("bank_id")(event.target.value)}
            disabled={mode === "edit" || submitting}
            options={bankOptions}
            placeholder={mode === "create" ? "Choisir une banque" : undefined}
            invalid={!!errors.bank_id}
            autoFocus={mode === "create"}
          />
        </Field>
        <Field
          label="Devise"
          htmlFor="account-devise"
          required={mode === "create"}
          error={errors.devise}
        >
          <Select
            id="account-devise"
            value={values.devise}
            onChange={(event) => set("devise")(event.target.value)}
            disabled={mode === "edit" || values.type_compte === "DH convertible" || submitting}
            options={currencyOptions}
            invalid={!!errors.devise}
          />
        </Field>
      </div>
      {mode === "edit" && (
        <p className="-mt-2 text-xs text-simtis-muted">
          Banque et devise ne sont plus modifiables : l&apos;historique des soldes en dépend.
        </p>
      )}

      <Field label="Type de compte" htmlFor="account-type" error={errors.type_compte}>
        <Select
          id="account-type"
          value={values.type_compte}
          onChange={(event) => changeType(event.target.value as TypeCompte)}
          disabled={submitting}
          options={TYPE_COMPTE_OPTIONS}
          invalid={!!errors.type_compte}
        />
      </Field>

      <Field label="Libellé" htmlFor="account-libelle" required error={errors.libelle}>
        <TextInput
          id="account-libelle"
          value={values.libelle}
          onChange={(event) => set("libelle")(event.target.value)}
          disabled={submitting}
          maxLength={120}
          autoFocus={mode === "edit"}
          invalid={!!errors.libelle}
          placeholder="Compte courant"
        />
      </Field>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="Numéro (RIB)"
          htmlFor="account-numero"
          required
          error={errors.numero}
          hint="Les espaces sont ignorés."
        >
          <TextInput
            id="account-numero"
            value={values.numero}
            onChange={(event) => set("numero")(event.target.value)}
            disabled={submitting}
            maxLength={60}
            autoComplete="off"
            invalid={!!errors.numero}
          />
        </Field>
        <Field
          label="Compte comptable"
          htmlFor="account-compte"
          error={errors.compte_comptable}
          hint="Compte Sage, ex. 5141."
        >
          <TextInput
            id="account-compte"
            value={values.compte_comptable}
            onChange={(event) => set("compte_comptable")(event.target.value)}
            disabled={submitting}
            maxLength={20}
            autoComplete="off"
            invalid={!!errors.compte_comptable}
          />
        </Field>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label={`LIGNE (${deviseSuffix})`}
          htmlFor="account-ligne"
          required
          error={errors.credit_autorise}
          hint="Crédit autorisé."
        >
          <NumberInput
            id="account-ligne"
            value={values.credit_autorise}
            onChange={(event) => set("credit_autorise")(event.target.value)}
            disabled={submitting}
            inputMode="decimal"
            invalid={!!errors.credit_autorise}
          />
        </Field>
        <Field
          label="Taux d'intérêt (%)"
          htmlFor="account-taux"
          error={errors.taux}
          hint="Vide si aucun."
        >
          <NumberInput
            id="account-taux"
            value={values.taux}
            onChange={(event) => set("taux")(event.target.value)}
            disabled={submitting}
            inputMode="decimal"
            invalid={!!errors.taux}
            placeholder="4,5"
          />
        </Field>
      </div>
    </FormModal>
  );
}
