import { cn } from "@/lib/cn";
import type { Status } from "@/types/status";

const SUCCESS = "bg-simtis-success-bg text-simtis-success-fg";
const WARNING = "bg-simtis-warning-bg text-simtis-warning-fg";
const DANGER = "bg-simtis-danger-bg text-simtis-danger-fg";
const ORANGE = "bg-simtis-orange-bg text-simtis-orange-fg";
const NEUTRAL = "bg-simtis-neutral-bg text-simtis-neutral-fg";
const PLANNED = "bg-simtis-light text-simtis-primary";

/** Seul endroit où un statut est associé à une couleur. */
const STATUS_STYLES: Record<Status, string> = {
  Rapprochée: SUCCESS,
  Réalisé: SUCCESS,
  Conforme: SUCCESS,
  Actif: SUCCESS,
  "À vérifier": WARNING,
  "En attente": WARNING,
  "Non rapprochée": DANGER,
  "À traiter": DANGER,
  Écart: ORANGE,
  "En cours": ORANGE,
  Prévu: PLANNED,
  Reporté: NEUTRAL,
  Clôturé: NEUTRAL,
  Traité: NEUTRAL,
  Annulé: NEUTRAL,
  Inactif: NEUTRAL,
};

export function StatusBadge({ status, className }: { status: Status; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap",
        STATUS_STYLES[status],
        className,
      )}
    >
      {status}
    </span>
  );
}
