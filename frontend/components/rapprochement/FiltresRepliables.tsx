"use client";

import { ChevronDown, SlidersHorizontal } from "lucide-react";
import { useSyncExternalStore, type ReactNode } from "react";

import { cn } from "@/lib/cn";
import { repli, type Repli } from "@/lib/repli";

// Filtres des volets du rapprochement, repliés par défaut pour laisser la place aux lignes
// (27/10/2026) ; le choix de chaque volet est gardé dans le navigateur.
const REPLIS: Record<"operations" | "ecritures", Repli> = {
  operations: repli("simtis.rapprochement.filtres-operations", false),
  ecritures: repli("simtis.rapprochement.filtres-ecritures", false),
};

export function FiltresRepliables({
  volet,
  actifs,
  children,
}: {
  volet: keyof typeof REPLIS;
  /** Nombre de filtres en cours, rappelé sur le bouton quand les filtres sont repliés. */
  actifs: number;
  children: ReactNode;
}) {
  const etat = REPLIS[volet];
  const ouverts = useSyncExternalStore(etat.subscribe, etat.lire, () => false);
  const id = `rapprochement-filtres-${volet}`;

  return (
    <div className="mb-3">
      <button
        type="button"
        onClick={() => etat.ecrire(!ouverts)}
        aria-expanded={ouverts}
        aria-controls={id}
        className="inline-flex items-center gap-2 rounded-[10px] px-2 py-1 text-sm font-medium text-simtis-primary-dark hover:bg-simtis-light"
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
      {ouverts && (
        <div id={id} className="mt-2">
          {children}
        </div>
      )}
    </div>
  );
}
