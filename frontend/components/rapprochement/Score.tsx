import { cn } from "@/lib/cn";
import { formatScore } from "@/lib/reconciliation";
import type { Critere } from "@/types/reconciliation";

/** Score sur 100 : vert pour une forte correspondance, orange sinon (toujours validée par un humain). */
export function ScoreBadge({ score, forte }: { score: string | null; forte: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap tabular-nums",
        forte
          ? "bg-simtis-success-bg text-simtis-success-fg"
          : "bg-simtis-warning-bg text-simtis-warning-fg",
      )}
    >
      Score {formatScore(score)}
    </span>
  );
}

/** Points obtenus par critère (référence, montant, date, libellé, tiers). */
export function ScoreDetail({ criteres }: { criteres: Critere[] }) {
  return (
    <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-[13px]">
      {criteres.map((critere) => (
        <div key={critere.code} className="contents">
          <dt className="text-simtis-muted">{critere.libelle}</dt>
          <dd
            className={cn(
              "text-right tabular-nums",
              Number(critere.points) > 0 ? "font-medium text-simtis-text" : "text-simtis-muted",
            )}
          >
            {formatScore(critere.points)}
          </dd>
        </div>
      ))}
    </dl>
  );
}
