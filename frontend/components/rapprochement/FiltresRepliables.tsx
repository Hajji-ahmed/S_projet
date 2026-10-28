"use client";

import { ChevronDown, SlidersHorizontal } from "lucide-react";
import { useSyncExternalStore, type ReactNode } from "react";

import { cn } from "@/lib/cn";
import { repli, type Repli } from "@/lib/repli";

// Filtres des volets du rapprochement, repliés par défaut pour laisser la place aux lignes
// (27/10/2026) ; le choix de chaque volet est gardé dans le navigateur. Depuis le 28/10/2026 le
// bouton est sur la ligne du titre du volet et les filtres se déplient dessous.
const REPLIS: Record<"operations" | "ecritures", Repli> = {
  operations: repli("simtis.rapprochement.filtres-operations", false),
  ecritures: repli("simtis.rapprochement.filtres-ecritures", false),
};

type Volet = keyof typeof REPLIS;

function useOuverts(volet: Volet): boolean {
  const etat = REPLIS[volet];
  return useSyncExternalStore(etat.subscribe, etat.lire, () => false);
}

const idDe = (volet: Volet) => `rapprochement-filtres-${volet}`;

/** Bouton « Filtres », à placer dans l'en-tête du volet. */
export function BoutonFiltres({
  volet,
  actifs,
}: {
  volet: Volet;
  /** Nombre de filtres en cours, rappelé sur le bouton. */
  actifs: number;
}) {
  const ouverts = useOuverts(volet);
  return (
    <button
      type="button"
      onClick={() => REPLIS[volet].ecrire(!ouverts)}
      aria-expanded={ouverts}
      aria-controls={idDe(volet)}
      className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-sm font-medium text-simtis-primary-dark hover:bg-simtis-light"
    >
      <SlidersHorizontal className="h-4 w-4" aria-hidden />
      Filtres
      {actifs > 0 && (
        <span className="rounded-full bg-simtis-primary px-2 py-0.5 text-xs font-semibold text-white">
          {actifs} actif{actifs > 1 ? "s" : ""}
        </span>
      )}
      <ChevronDown
        className={cn(
          "h-4 w-4 text-simtis-muted transition-transform duration-200",
          ouverts && "rotate-180",
        )}
        aria-hidden
      />
    </button>
  );
}

/** Les filtres eux-mêmes, affichés seulement quand le bouton les a dépliés. */
export function FiltresRepliables({ volet, children }: { volet: Volet; children: ReactNode }) {
  const ouverts = useOuverts(volet);
  if (!ouverts) return null;
  return (
    <div id={idDe(volet)} className="mb-2">
      {children}
    </div>
  );
}
