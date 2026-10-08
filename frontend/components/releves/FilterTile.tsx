import { cn } from "@/lib/cn";

type FilterTileProps = {
  label: string;
  value: number;
  /** Classe de couleur du chiffre (token `simtis-*`). */
  tone: string;
  /** Tuile qui filtre le tableau en ce moment : surlignée. */
  active: boolean;
  onClick: () => void;
};

/** Tuile chiffrée cliquable de l'étape Validation : un clic filtre le tableau, un second l'annule. */
export function FilterTile({ label, value, tone, active, onClick }: FilterTileProps) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      title={active ? "Afficher toutes les lignes" : `Afficher seulement : ${label.toLowerCase()}`}
      className={cn(
        "rounded-[12px] border px-4 py-3 text-left transition-colors duration-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-simtis-secondary",
        active
          ? "border-simtis-primary bg-simtis-light"
          : "border-simtis-border bg-simtis-card hover:bg-simtis-light/50",
      )}
    >
      <span className="block text-xs text-simtis-muted">{label}</span>
      <span className={cn("mt-1 block text-2xl font-semibold tabular-nums", tone)}>{value}</span>
    </button>
  );
}
