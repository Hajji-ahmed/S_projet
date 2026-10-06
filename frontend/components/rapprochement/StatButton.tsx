import { cn } from "@/lib/cn";

type StatButtonProps = {
  label: string;
  value: number | undefined;
  /** Compteur qui filtre la liste en ce moment : surligné. */
  active: boolean;
  onClick: () => void;
  /** Texte lu par les lecteurs d'écran, ex. « Filtrer sur À vérifier ». */
  description?: string;
};

/** Compteur cliquable d'un résumé : un clic filtre (ou ouvre) la liste correspondante. */
export function StatButton({ label, value, active, onClick, description }: StatButtonProps) {
  return (
    <button
      type="button"
      aria-pressed={active}
      title={description}
      onClick={onClick}
      className={cn(
        "rounded-[10px] border px-3 py-2 text-left transition-colors duration-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-simtis-secondary",
        active
          ? "border-simtis-primary bg-simtis-light"
          : "border-transparent hover:border-simtis-border hover:bg-simtis-light/50",
      )}
    >
      <span className="block text-simtis-muted">{label}</span>
      <span className="block text-[17px] font-semibold text-simtis-primary-dark tabular-nums">
        {value ?? "-"}
      </span>
    </button>
  );
}
