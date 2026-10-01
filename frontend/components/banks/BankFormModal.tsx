"use client";

import { Landmark } from "lucide-react";
import Image from "next/image";
import { useState } from "react";

import { Field, NumberInput, Select, TextInput } from "@/components/ui/Field";
import { FormModal } from "@/components/ui/FormModal";
import { ApiError } from "@/lib/api";
import {
  BANK_LOGOS,
  parseOrder,
  validateBankForm,
  type BankFormErrors,
  type BankFormValues,
} from "@/lib/banks";
import { createBank, updateBank } from "@/services/banks";
import type { Bank } from "@/types/bank";

type BankFormModalProps = {
  /** Banque à modifier ; absente = création. */
  bank?: Bank;
  onClose: () => void;
  onSaved: (bank: Bank, mode: "create" | "edit") => void;
};

function initialValues(bank?: Bank): BankFormValues {
  return bank
    ? { code: bank.code, nom: bank.nom, logo: bank.logo ?? "", ordre: String(bank.ordre_affichage) }
    : { code: "", nom: "", logo: "", ordre: "" };
}

/** À monter seulement quand la fenêtre est ouverte : son état repart de zéro à chaque ouverture. */
export function BankFormModal({ bank, onClose, onSaved }: BankFormModalProps) {
  const mode = bank ? "edit" : "create";
  const [values, setValues] = useState<BankFormValues>(() => initialValues(bank));
  const [errors, setErrors] = useState<BankFormErrors>({});
  const [apiError, setApiError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const set = (field: keyof BankFormValues) => (value: string) =>
    setValues((current) => ({ ...current, [field]: value }));

  async function handleSubmit() {
    const found = validateBankForm(values, mode);
    setErrors(found);
    setApiError(null);
    if (Object.keys(found).length > 0) return;

    setSubmitting(true);
    const logo = values.logo || null;
    try {
      const saved = bank
        ? await updateBank(bank.id, {
            nom: values.nom.trim(),
            logo,
            ordre_affichage: Number(values.ordre.trim()),
          })
        : await createBank({
            code: values.code.trim().toUpperCase(),
            nom: values.nom.trim(),
            logo,
            ordre_affichage: parseOrder(values.ordre),
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
      title={bank ? `Modifier la banque ${bank.code}` : "Nouvelle banque"}
      onClose={onClose}
      onSubmit={handleSubmit}
      submitting={submitting}
      error={apiError}
    >
      <Field
        label="Code"
        htmlFor="bank-code"
        required={mode === "create"}
        error={errors.code}
        hint={
          mode === "edit"
            ? "Non modifiable après la création."
            : "Affiché dans les colonnes des tableaux (ex. AWB)."
        }
      >
        <TextInput
          id="bank-code"
          value={values.code}
          onChange={(event) => set("code")(event.target.value.toUpperCase())}
          disabled={mode === "edit" || submitting}
          maxLength={10}
          autoComplete="off"
          autoFocus={mode === "create"}
          invalid={!!errors.code}
          placeholder="CDM"
        />
      </Field>

      <Field label="Nom" htmlFor="bank-nom" required error={errors.nom}>
        <TextInput
          id="bank-nom"
          value={values.nom}
          onChange={(event) => set("nom")(event.target.value)}
          disabled={submitting}
          maxLength={120}
          autoFocus={mode === "edit"}
          invalid={!!errors.nom}
          placeholder="Crédit du Maroc"
        />
      </Field>

      <Field label="Logo" htmlFor="bank-logo" error={errors.logo}>
        <div className="flex items-center gap-3">
          <span className="grid h-[42px] w-[42px] shrink-0 place-items-center overflow-hidden rounded-lg border border-simtis-border bg-simtis-card">
            {values.logo ? (
              <Image
                src={values.logo}
                alt=""
                width={36}
                height={36}
                className="h-9 w-9 object-contain"
              />
            ) : (
              <Landmark className="h-5 w-5 text-simtis-muted" aria-hidden />
            )}
          </span>
          <Select
            id="bank-logo"
            value={values.logo}
            onChange={(event) => set("logo")(event.target.value)}
            disabled={submitting}
            options={BANK_LOGOS}
            placeholder="Aucun logo"
            invalid={!!errors.logo}
          />
        </div>
      </Field>

      <Field
        label="Ordre d'affichage"
        htmlFor="bank-ordre"
        required={mode === "edit"}
        error={errors.ordre}
        hint={
          mode === "create"
            ? "Position de la colonne dans les tableaux. Vide : en dernier."
            : "Position de la colonne dans les tableaux."
        }
      >
        <NumberInput
          id="bank-ordre"
          value={values.ordre}
          onChange={(event) => set("ordre")(event.target.value)}
          disabled={submitting}
          maxLength={3}
          invalid={!!errors.ordre}
          className="max-w-[120px]"
        />
      </Field>
    </FormModal>
  );
}
