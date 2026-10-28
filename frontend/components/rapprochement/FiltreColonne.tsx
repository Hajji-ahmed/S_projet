"use client";

import { Check, Funnel, FunnelX } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { Button } from "@/components/ui/Button";
import { DateInput, Field, TextInput } from "@/components/ui/Field";
import { cn } from "@/lib/cn";
import { TYPES_OPERATION, type FiltresVolet } from "@/lib/reconciliation";

// Filtres des volets du rapprochement dans les en-têtes de colonnes, comme dans Excel (28/10/2026) :
// un entonnoir gris au repos, turquoise plein quand la colonne est filtrée, qui ouvre un petit menu.
// Le menu est rendu dans <body> : le cadre du tableau défile et le couperait.

const LARGEUR = 248;
const MARGE = 8;

type FiltreColonneProps = {
  /** Nom de la colonne, lu par les lecteurs d'écran (« Filtrer la colonne Date »). */
  colonne: string;
  actif: boolean;
  /** Contenu du menu ; `fermer` le referme après un choix. */
  children: (fermer: () => void) => ReactNode;
};

export function FiltreColonne({ colonne, actif, children }: FiltreColonneProps) {
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null);
  const boutonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const ouvert = position !== null;
  const fermer = () => setPosition(null);

  const ouvrir = () => {
    const rect = boutonRef.current?.getBoundingClientRect();
    if (!rect) return;
    const left = Math.max(MARGE, Math.min(rect.left, window.innerWidth - LARGEUR - MARGE));
    setPosition({ top: rect.bottom + 4, left });
  };

  useEffect(() => {
    if (!ouvert) return;
    const dedans = (cible: EventTarget | null) =>
      cible instanceof Node &&
      (menuRef.current?.contains(cible) || boutonRef.current?.contains(cible));
    const surEchap = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setPosition(null);
        boutonRef.current?.focus();
      }
    };
    const surClic = (event: MouseEvent) => {
      if (!dedans(event.target)) setPosition(null);
    };
    // Le tableau défile sous le menu : il se referme plutôt que de flotter au mauvais endroit
    const surDefilement = (event: Event) => {
      if (!dedans(event.target)) setPosition(null);
    };
    const surRedimension = () => setPosition(null);
    window.addEventListener("keydown", surEchap);
    window.addEventListener("mousedown", surClic);
    window.addEventListener("scroll", surDefilement, true);
    window.addEventListener("resize", surRedimension);
    return () => {
      window.removeEventListener("keydown", surEchap);
      window.removeEventListener("mousedown", surClic);
      window.removeEventListener("scroll", surDefilement, true);
      window.removeEventListener("resize", surRedimension);
    };
  }, [ouvert]);

  // Premier champ du menu sous le doigt dès l'ouverture
  useLayoutEffect(() => {
    if (!ouvert) return;
    menuRef.current
      ?.querySelector<HTMLElement>("input, button[aria-pressed='true'], button")
      ?.focus();
  }, [ouvert]);

  return (
    <>
      <button
        ref={boutonRef}
        type="button"
        onClick={() => (ouvert ? fermer() : ouvrir())}
        aria-haspopup="dialog"
        aria-expanded={ouvert}
        aria-label={`Filtrer la colonne ${colonne}${actif ? " (filtre en cours)" : ""}`}
        title={actif ? "Filtre en cours" : "Filtrer"}
        className={cn(
          "inline-grid h-5 w-5 shrink-0 place-items-center rounded transition-colors duration-150",
          actif
            ? "text-simtis-secondary hover:bg-simtis-card"
            : "text-simtis-muted/70 hover:bg-simtis-card hover:text-simtis-primary",
          ouvert && "bg-simtis-card",
        )}
      >
        <Funnel className={cn("h-3 w-3", actif && "fill-current")} aria-hidden />
      </button>
      {ouvert &&
        createPortal(
          <div
            ref={menuRef}
            role="dialog"
            aria-label={`Filtre de la colonne ${colonne}`}
            style={{ top: position.top, left: position.left, width: LARGEUR }}
            className="fixed z-50 rounded-xl border border-simtis-border bg-simtis-card p-3 text-left text-sm font-normal text-simtis-text shadow-simtis-hover"
          >
            {children(fermer)}
          </div>,
          document.body,
        )}
    </>
  );
}

/** Liste de choix (un seul à la fois) : un clic applique le filtre et referme le menu. */
export function ChoixFiltre({
  titre,
  options,
  valeur,
  onChoisir,
}: {
  titre?: string;
  options: readonly { value: string; label: string }[];
  valeur: string;
  onChoisir: (valeur: string) => void;
}) {
  return (
    <div role="group" aria-label={titre}>
      {titre && <p className="mb-1 text-xs font-semibold text-simtis-muted">{titre}</p>}
      <ul className="space-y-0.5">
        {options.map((option) => {
          const choisi = option.value === valeur;
          return (
            <li key={option.value || "tous"}>
              <button
                type="button"
                aria-pressed={choisi}
                onClick={() => onChoisir(option.value)}
                className={cn(
                  "flex w-full items-center gap-2 rounded-lg px-2 py-1 text-left hover:bg-simtis-light",
                  choisi && "font-medium text-simtis-primary-dark",
                )}
              >
                <Check
                  className={cn("h-3.5 w-3.5 shrink-0", choisi ? "opacity-100" : "opacity-0")}
                  aria-hidden
                />
                {option.label}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** Du / Au, limités à la période de l'écran ; appliqués avec le bouton. */
export function FiltreDates({
  id,
  du,
  au,
  min,
  max,
  onAppliquer,
}: {
  id: string;
  du: string;
  au: string;
  min: string;
  max: string;
  onAppliquer: (du: string, au: string) => void;
}) {
  const [debut, setDebut] = useState(du);
  const [fin, setFin] = useState(au);
  return (
    <form
      className="space-y-2"
      onSubmit={(event) => {
        event.preventDefault();
        onAppliquer(debut, fin);
      }}
    >
      <Field label="Du" htmlFor={`${id}-du`}>
        <DateInput
          id={`${id}-du`}
          value={debut}
          min={min}
          max={max}
          onChange={(event) => setDebut(event.target.value)}
        />
      </Field>
      <Field label="Au" htmlFor={`${id}-au`}>
        <DateInput
          id={`${id}-au`}
          value={fin}
          min={min}
          max={max}
          onChange={(event) => setFin(event.target.value)}
        />
      </Field>
      <PiedMenu onEffacer={() => onAppliquer("", "")} effacable={!!(du || au)} />
    </form>
  );
}

/** Menu de la colonne Libellé : recherche, puis type d'opération. Il reste ouvert pour combiner
 * les deux. */
export function FiltreLibelle({
  id,
  filtres,
  placeholder,
  onChanger,
}: {
  id: string;
  filtres: FiltresVolet;
  placeholder: string;
  onChanger: (modif: Partial<FiltresVolet>) => void;
}) {
  return (
    <div className="space-y-3">
      <FiltreRecherche
        id={id}
        q={filtres.q}
        placeholder={placeholder}
        onAppliquer={(q) => onChanger({ q })}
      />
      <ChoixFiltre
        titre="Type"
        options={OPTIONS_TYPE}
        valeur={filtres.typeOperation}
        onChoisir={(typeOperation) => onChanger({ typeOperation })}
      />
      <div className="border-t border-simtis-border pt-2">
        <button
          type="button"
          onClick={() => onChanger({ q: "", typeOperation: "" })}
          disabled={!filtres.q && !filtres.typeOperation}
          className="text-xs font-medium text-simtis-primary hover:underline disabled:pointer-events-none disabled:opacity-40"
        >
          Effacer
        </button>
      </div>
    </div>
  );
}

const OPTIONS_TYPE = [
  { value: "", label: "Tous les types" },
  ...TYPES_OPERATION.map((item) => ({ value: item, label: item })),
];

/** Entonnoir des colonnes Débit et Crédit : un seul sens à la fois (filtre « Sens »). */
export function FiltreSens({
  colonne,
  actif,
  sens,
  onChanger,
}: {
  colonne: "Débit" | "Crédit";
  actif: boolean;
  sens: string;
  onChanger: (modif: Partial<FiltresVolet>) => void;
}) {
  return (
    <FiltreColonne colonne={colonne} actif={actif}>
      {(fermer) => (
        <ChoixFiltre
          titre="Sens"
          options={[
            { value: "", label: "Débits et crédits" },
            {
              value: colonne,
              label: colonne === "Débit" ? "Seulement les débits" : "Seulement les crédits",
            },
          ]}
          valeur={sens === colonne ? colonne : ""}
          onChoisir={(valeur) => {
            // « Débits et crédits » depuis l'autre colonne ne touche pas au sens choisi ailleurs
            if (valeur || sens === colonne) onChanger({ sens: valeur });
            fermer();
          }}
        />
      )}
    </FiltreColonne>
  );
}

/** « Effacer les filtres », sur la ligne du titre du volet, seulement quand un filtre est en cours. */
export function EffacerFiltres({
  visible,
  onEffacer,
}: {
  visible: boolean;
  onEffacer: () => void;
}) {
  if (!visible) return null;
  return (
    <button
      type="button"
      onClick={onEffacer}
      className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-simtis-primary-dark hover:bg-simtis-light"
    >
      <FunnelX className="h-3.5 w-3.5" aria-hidden />
      Effacer les filtres
    </button>
  );
}

/** Recherche dans le libellé : appliquée après une courte pause de frappe, ou avec Entrée. */
function FiltreRecherche({
  id,
  q,
  placeholder,
  onAppliquer,
}: {
  id: string;
  q: string;
  placeholder: string;
  onAppliquer: (q: string) => void;
}) {
  const [texte, setTexte] = useState(q);
  const appliquerRef = useRef(onAppliquer);
  useEffect(() => {
    appliquerRef.current = onAppliquer;
  });
  useEffect(() => {
    const valeur = texte.trim();
    if (valeur === q) return;
    const minuterie = window.setTimeout(() => appliquerRef.current(valeur), 500);
    return () => window.clearTimeout(minuterie);
  }, [texte, q]);
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onAppliquer(texte.trim());
      }}
    >
      <Field label="Rechercher" htmlFor={`${id}-q`}>
        <TextInput
          id={`${id}-q`}
          value={texte}
          maxLength={100}
          placeholder={placeholder}
          onChange={(event) => setTexte(event.target.value)}
        />
      </Field>
    </form>
  );
}

/** Bas d'un menu à saisie : « Effacer » et « Appliquer ». */
function PiedMenu({ onEffacer, effacable }: { onEffacer: () => void; effacable: boolean }) {
  return (
    <div className="flex items-center justify-between gap-2 pt-1">
      <button
        type="button"
        onClick={onEffacer}
        disabled={!effacable}
        className="text-xs font-medium text-simtis-primary hover:underline disabled:pointer-events-none disabled:opacity-40"
      >
        Effacer
      </button>
      <Button type="submit" variant="primary">
        Appliquer
      </Button>
    </div>
  );
}
