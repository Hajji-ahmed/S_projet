/**
 * Logos disponibles pour une banque : les fichiers de `public/banques/`. Pour en ajouter un, déposer le
 * fichier dans ce dossier puis l'ajouter ici (l'API n'accepte que des chemins `/banques/...`).
 */
export const BANK_LOGOS: readonly { value: string; label: string }[] = [
  { value: "/banques/attijariwafa.png", label: "Attijariwafa" },
  { value: "/banques/bmce.png", label: "BMCE" },
  { value: "/banques/bmci.png", label: "BMCI" },
  { value: "/banques/bp.png", label: "BP" },
  { value: "/banques/cih.png", label: "CIH" },
];

export const MAX_DISPLAY_ORDER = 999;

export type BankFormValues = {
  code: string;
  nom: string;
  logo: string;
  /** Texte saisi : vide = placement automatique en dernière position (création uniquement). */
  ordre: string;
};

export type BankFormErrors = Partial<Record<keyof BankFormValues, string>>;

/** Mêmes règles que l'API (`backend/app/schemas/bank.py`), pour signaler l'erreur avant l'envoi. */
export function validateBankForm(values: BankFormValues, mode: "create" | "edit"): BankFormErrors {
  const errors: BankFormErrors = {};

  if (mode === "create" && !/^[A-Z0-9]{2,10}$/.test(values.code.trim().toUpperCase())) {
    errors.code = "2 à 10 lettres ou chiffres, sans espace (ex. AWB).";
  }

  const nom = values.nom.trim();
  if (nom.length < 2 || nom.length > 120) {
    errors.nom = "Le nom doit contenir entre 2 et 120 caractères.";
  }

  const ordre = values.ordre.trim();
  if (ordre === "" && mode === "edit") {
    errors.ordre = "L'ordre d'affichage est obligatoire.";
  } else if (ordre !== "") {
    const value = Number(ordre);
    if (!Number.isInteger(value) || value < 0 || value > MAX_DISPLAY_ORDER) {
      errors.ordre = `Un nombre entier entre 0 et ${MAX_DISPLAY_ORDER}.`;
    }
  }

  if (values.logo && !BANK_LOGOS.some((logo) => logo.value === values.logo)) {
    errors.logo = "Choisissez un logo de la liste.";
  }

  return errors;
}

export function parseOrder(ordre: string): number | null {
  return ordre.trim() === "" ? null : Number(ordre.trim());
}
