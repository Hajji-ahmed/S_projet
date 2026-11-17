"use client";

import { useState } from "react";

import { Field, TextInput } from "@/components/ui/Field";
import { FormModal } from "@/components/ui/FormModal";
import { ApiError } from "@/lib/api";
import {
  codeDepuisNom,
  nomPropre,
  validateSocieteForm,
  type SocieteFormErrors,
  type SocieteFormValues,
} from "@/lib/societes";
import { createCompany, updateCompany } from "@/services/referentiel";
import type { CompanyAdmin } from "@/types/company";

type SocieteFormModalProps = {
  /** Société à renommer ; absente = création. */
  societe?: CompanyAdmin;
  onClose: () => void;
  onSaved: (societe: CompanyAdmin, mode: "create" | "edit") => void;
};

/** À monter seulement quand la fenêtre est ouverte : son état repart de zéro à chaque ouverture. */
export function SocieteFormModal({ societe, onClose, onSaved }: SocieteFormModalProps) {
  const mode = societe ? "edit" : "create";
  const [values, setValues] = useState<SocieteFormValues>({
    code: societe?.code ?? "",
    nom: societe?.nom ?? "",
  });
  // Tant que l'utilisateur n'a pas touché au code, il suit le nom
  const [codeSaisi, setCodeSaisi] = useState(false);
  const [errors, setErrors] = useState<SocieteFormErrors>({});
  const [apiError, setApiError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function changeNom(nom: string) {
    setValues((current) => ({
      nom,
      code: mode === "create" && !codeSaisi ? codeDepuisNom(nom) : current.code,
    }));
  }

  async function handleSubmit() {
    const found = validateSocieteForm(values, mode);
    setErrors(found);
    setApiError(null);
    if (Object.keys(found).length > 0) return;

    setSubmitting(true);
    try {
      const saved = societe
        ? await updateCompany(societe.id, { nom: nomPropre(values.nom) })
        : await createCompany({
            code: values.code.trim().toUpperCase(),
            nom: nomPropre(values.nom),
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
      title={societe ? `Modifier la société ${societe.code}` : "Nouvelle société"}
      onClose={onClose}
      onSubmit={handleSubmit}
      submitLabel={mode === "create" ? "Créer la société" : "Enregistrer"}
      submitting={submitting}
      error={apiError}
    >
      <Field label="Nom" htmlFor="societe-nom" required error={errors.nom}>
        <TextInput
          id="societe-nom"
          value={values.nom}
          onChange={(event) => changeNom(event.target.value)}
          disabled={submitting}
          maxLength={120}
          autoFocus
          autoComplete="off"
          invalid={!!errors.nom}
          placeholder="Société Atlas"
        />
      </Field>

      <Field
        label="Code"
        htmlFor="societe-code"
        required={mode === "create"}
        error={errors.code}
        hint={
          mode === "edit"
            ? "Non modifiable après la création."
            : "Proposé à partir du nom, modifiable. Non modifiable après la création."
        }
      >
        <TextInput
          id="societe-code"
          value={values.code}
          onChange={(event) => {
            setCodeSaisi(true);
            setValues((current) => ({ ...current, code: event.target.value.toUpperCase() }));
          }}
          disabled={mode === "edit" || submitting}
          maxLength={20}
          autoComplete="off"
          invalid={!!errors.code}
          placeholder="ATLAS"
          className="max-w-[220px] font-mono"
        />
      </Field>
    </FormModal>
  );
}
