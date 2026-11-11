import { cn } from "@/lib/cn";
import { formatAmount } from "@/lib/format";

type StatButtonProps = {
  label: string;
  value: number | undefined;
  /** Compteur qui filtre la liste en ce moment : surligné. */
  active: boolean;
  onClick: () => void;
  /** Texte lu par les lecteurs d'écran, ex. « Filtrer sur À vérifier ». */
  description?: string;
  /** Précision sous la valeur, ex. « 90 % » (11/11/2026). */
  detail?: string;
  /** « tuile » : carte blanche bordée, pour la rangée de compteurs du Rapprochement (11/11/2026). */
  variant?: "compact" | "tuile";
};

/** Compteur cliquable d'un résumé : un clic filtre (ou ouvre) la liste correspondante. */
export function StatButton({
  label,
  value,
  active,
  onClick,
  description,
  detail,
  variant = "compact",
}: StatButtonProps) {
  const tuile = variant === "tuile";
  return (
    <button
      type="button"
      aria-pressed={active}
      title={description}
      onClick={onClick}
      className={cn(
        "text-left transition-colors duration-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-simtis-secondary",
        tuile ? "rounded-card border px-5 py-4 shadow-simtis" : "rounded-[10px] border px-3 py-2",
        active
          ? "border-simtis-primary bg-simtis-light"
          : tuile
            ? "border-simtis-border bg-simtis-card hover:border-simtis-primary hover:bg-simtis-light/50"
            : "border-transparent hover:border-simtis-border hover:bg-simtis-light/50",
      )}
    >
      <span className={cn("block text-simtis-muted", tuile && "text-sm")}>{label}</span>
      <span className="flex items-baseline gap-2">
        <span
          className={cn(
            "block font-semibold text-simtis-primary-dark tabular-nums",
            tuile ? "text-[24px] leading-tight" : "text-[17px]",
          )}
        >
          {value === undefined ? "-" : formatAmount(value)}
        </span>
        {detail && (
          <span className="text-sm font-medium text-simtis-muted tabular-nums">{detail}</span>
        )}
      </span>
    </button>
  );
}
