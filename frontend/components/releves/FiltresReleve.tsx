"use client";

import { useState } from "react";

import { ChoixFiltre, PiedMenu } from "@/components/rapprochement/FiltreColonne";
import { Field, TextInput } from "@/components/ui/Field";
import { normalizeAmountInput } from "@/lib/accounts";
import { LIBELLE_A_CHOISIR, type FiltresReleve, type SensMontant } from "@/lib/filtresReleve";
import { toCents } from "@/lib/statementLines";

// Menus des filtres du relevé par compte (12/11/2026), ouverts depuis les entonnoirs des en-têtes
// (`FiltreColonne` de l'écran Rapprochement).

/** Pointages à cocher, comme la liste d'un filtre Excel ; chaque case s'applique aussitôt. */
export function FiltrePointage({
  options,
  coches,
  onChanger,
}: {
  options: readonly (string | null)[];
  /** Vide = tous les pointages. */
  coches: readonly (string | null)[];
  onChanger: (pointages: (string | null)[]) => void;
}) {
  const tous = coches.length === 0;
  const estCoche = (option: string | null) => tous || coches.includes(option);
  const nbCoches = tous ? options.length : coches.length;

  function basculer(option: string | null) {
    const actuels = tous ? [...options] : [...coches];
    const suivants = actuels.includes(option)
      ? actuels.filter((item) => item !== option)
      : [...actuels, option];
    // Tout coché revient à « aucun filtre »
    onChanger(options.every((item) => suivants.includes(item)) ? [] : suivants);
  }

  if (options.length === 0) {
    return <p className="text-simtis-muted">Aucune opération sur cette période.</p>;
  }
  return (
    <div className="space-y-2" role="group" aria-label="Pointage">
      <label className="flex items-center gap-2 rounded-lg px-2 py-1 font-medium hover:bg-simtis-light">
        <input
          type="checkbox"
          className="h-4 w-4 accent-simtis-primary"
          checked={tous}
          disabled={tous}
          onChange={() => onChanger([])}
        />
        Tout sélectionner
      </label>
      <ul className="max-h-64 space-y-0.5 overflow-y-auto border-t border-simtis-border pt-2">
        {options.map((option) => (
          <li key={option ?? "a-choisir"}>
            <label className="flex items-center gap-2 rounded-lg px-2 py-1 hover:bg-simtis-light">
              <input
                type="checkbox"
                className="h-4 w-4 shrink-0 accent-simtis-primary"
                checked={estCoche(option)}
                // La dernière case cochée reste cochée : un filtre vide montrerait tout
                disabled={estCoche(option) && nbCoches === 1}
                onChange={() => basculer(option)}
              />
              <span className={option === null ? "text-simtis-warning-fg" : undefined}>
                {option ?? LIBELLE_A_CHOISIR}
              </span>
            </label>
          </li>
        ))}
      </ul>
    </div>
  );
}

type FiltreMontantValeurs = Pick<FiltresReleve, "sens" | "exact" | "min" | "max">;

const OPTIONS_SENS = [
  { value: "", label: "Débits et crédits" },
  { value: "Débit", label: "Seulement les débits" },
  { value: "Crédit", label: "Seulement les crédits" },
] as const;

/** « 12500.50 » → « 12500,50 » pour le champ. */
function versChamp(valeur: string): string {
  return valeur.replace(".", ",");
}

/** Montant exact, ou fourchette min / max, sur les débits, les crédits ou les deux. Appliqué avec
 * le bouton ; le même menu s'ouvre depuis Débit et depuis Crédit. */
export function FiltreMontant({
  id,
  valeurs,
  onAppliquer,
}: {
  id: string;
  valeurs: FiltreMontantValeurs;
  onAppliquer: (valeurs: FiltreMontantValeurs) => void;
}) {
  const [sens, setSens] = useState<SensMontant>(valeurs.sens);
  const [exact, setExact] = useState(versChamp(valeurs.exact));
  const [min, setMin] = useState(versChamp(valeurs.min));
  const [max, setMax] = useState(versChamp(valeurs.max));
  const [erreur, setErreur] = useState<string | null>(null);

  /** « » sans saisie, le montant normalisé, ou undefined s'il est invalide. */
  function lire(texte: string): string | undefined {
    const brut = texte.trim();
    if (!brut) return "";
    return normalizeAmountInput(brut) ?? undefined;
  }

  function appliquer() {
    const exactLu = lire(exact);
    const minLu = lire(min);
    const maxLu = lire(max);
    if (exactLu === undefined || minLu === undefined || maxLu === undefined) {
      setErreur("Montant invalide : chiffres et 2 décimales au plus (ex. 12 500,50).");
      return;
    }
    if (!exactLu && minLu && maxLu && toCents(minLu) > toCents(maxLu)) {
      setErreur("Le minimum dépasse le maximum.");
      return;
    }
    // Avec un montant exact, la fourchette ne sert pas
    onAppliquer({
      sens,
      exact: exactLu,
      min: exactLu ? "" : minLu,
      max: exactLu ? "" : maxLu,
    });
  }

  const effacable = !!(valeurs.sens || valeurs.exact || valeurs.min || valeurs.max);
  return (
    <form
      className="space-y-3"
      onSubmit={(event) => {
        event.preventDefault();
        appliquer();
      }}
    >
      <ChoixFiltre
        titre="Sens"
        options={OPTIONS_SENS}
        valeur={sens}
        onChoisir={(valeur) => setSens(valeur as SensMontant)}
      />
      <Field label="Montant exact" htmlFor={`${id}-exact`}>
        <TextInput
          id={`${id}-exact`}
          inputMode="decimal"
          value={exact}
          maxLength={25}
          placeholder="12 500,50"
          onChange={(event) => {
            setExact(event.target.value);
            setErreur(null);
          }}
        />
      </Field>
      <div className="grid grid-cols-2 gap-2">
        <Field label="Min" htmlFor={`${id}-min`}>
          <TextInput
            id={`${id}-min`}
            inputMode="decimal"
            value={min}
            maxLength={25}
            disabled={!!exact.trim()}
            onChange={(event) => {
              setMin(event.target.value);
              setErreur(null);
            }}
          />
        </Field>
        <Field label="Max" htmlFor={`${id}-max`}>
          <TextInput
            id={`${id}-max`}
            inputMode="decimal"
            value={max}
            maxLength={25}
            disabled={!!exact.trim()}
            onChange={(event) => {
              setMax(event.target.value);
              setErreur(null);
            }}
          />
        </Field>
      </div>
      {erreur && (
        <p role="alert" className="text-xs text-simtis-danger-fg">
          {erreur}
        </p>
      )}
      <PiedMenu
        effacable={effacable}
        onEffacer={() => onAppliquer({ sens: "", exact: "", min: "", max: "" })}
      />
    </form>
  );
}
