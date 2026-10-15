/** Paramètres (P16.3) : brouillon de la grille. Les bornes sont vérifiées par l'API. */
import type { Regle, RegleInput } from "@/types/parametres";

/** « 80.00 » → « 80 » ; « 3.000000 » → « 3 » : valeurs saisies sans zéros inutiles. */
export function nombreSaisi(valeur: string | null): string {
  if (valeur === null) return "";
  return valeur.includes(".") ? valeur.replace(/\.?0+$/, "") : valeur;
}

export function brouillonDe(regles: Regle[]): RegleInput[] {
  return regles.map((regle) => ({
    code: regle.code,
    poids: nombreSaisi(regle.poids),
    tolerance: regle.tolerance === null ? null : nombreSaisi(regle.tolerance),
    actif: regle.actif,
  }));
}

/** Règles dont le brouillon diffère de l'état enregistré (seules celles-ci sont envoyées). */
export function reglesModifiees(regles: Regle[], brouillon: RegleInput[]): RegleInput[] {
  const initial = new Map(brouillonDe(regles).map((r) => [r.code, r]));
  return brouillon.filter((r) => {
    const avant = initial.get(r.code);
    return (
      !avant ||
      avant.poids !== r.poids.trim() ||
      (avant.tolerance ?? "") !== (r.tolerance ?? "").trim() ||
      avant.actif !== r.actif
    );
  });
}
