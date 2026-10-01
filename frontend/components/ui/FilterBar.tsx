import { RotateCcw } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/Button";

type FilterBarProps = {
  children: ReactNode;
  /** Bouton « Réinitialiser », affiché seulement quand un filtre est actif. */
  onReset?: () => void;
  active?: boolean;
};

/** Barre de filtres au-dessus d'un tableau. Chaque filtre est un `Field` de largeur fixe. */
export function FilterBar({ children, onReset, active = false }: FilterBarProps) {
  return (
    <div
      role="search"
      aria-label="Filtres"
      className="flex flex-wrap items-end gap-3 rounded-[14px] border border-simtis-border bg-simtis-card p-4 shadow-simtis"
    >
      {children}
      {onReset && active && (
        <Button variant="ghost" icon={RotateCcw} onClick={onReset}>
          Réinitialiser
        </Button>
      )}
    </div>
  );
}

/** Conteneur d'un filtre : pleine largeur sur mobile, largeur fixe au-delà. */
export function FilterItem({ children }: { children: ReactNode }) {
  return <div className="w-full sm:w-48">{children}</div>;
}
