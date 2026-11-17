/** Règles du formulaire « Société » (17/11/2026). Le backend refait les mêmes contrôles. */

export const CODE_SOCIETE_PATTERN = /^[A-Z0-9_-]{2,20}$/;
const CODE_PROPOSE_MAX = 10;

/** Code proposé à partir du nom : sans accents, en majuscules, lettres et chiffres seulement.
 * « Société Atlas » → « SOCIETEATL ». L'utilisateur peut le modifier avant de créer. */
export function codeDepuisNom(nom: string): string {
  return nom
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, "")
    .slice(0, CODE_PROPOSE_MAX);
}

export type SocieteFormValues = { code: string; nom: string };
export type SocieteFormErrors = Partial<Record<keyof SocieteFormValues, string>>;

/** Nom espacé normalement, comme le backend le range. */
export function nomPropre(nom: string): string {
  return nom.split(/\s+/).filter(Boolean).join(" ");
}

export function validateSocieteForm(
  values: SocieteFormValues,
  mode: "create" | "edit",
): SocieteFormErrors {
  const errors: SocieteFormErrors = {};
  const nom = nomPropre(values.nom);
  if (!nom) errors.nom = "Le nom est obligatoire.";
  else if (nom.length > 120) errors.nom = "Le nom ne doit pas dépasser 120 caractères.";
  if (mode === "create" && !CODE_SOCIETE_PATTERN.test(values.code.trim().toUpperCase())) {
    errors.code = "2 à 20 lettres, chiffres, « _ » ou « - » (ex. SOCX).";
  }
  return errors;
}
