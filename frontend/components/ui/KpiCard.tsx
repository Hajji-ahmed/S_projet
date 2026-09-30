import { ArrowDown, ArrowUp, type LucideIcon } from "lucide-react";

import { cn } from "@/lib/cn";

type KpiCardProps = {
  title: string;
  /** Valeur déjà formatée, ex. « 2 450 000 DH » (voir `formatAmount`). */
  value: string;
  icon: LucideIcon;
  /** Variation, ex. « +5.2% ». Absente : la ligne de variation n'est pas affichée. */
  delta?: string;
  trend?: "up" | "down";
  deltaLabel?: string;
  /** Pourcentage 0-100 : affiche un anneau de progression à droite (ex. opérations rapprochées). */
  progress?: number;
};

export function KpiCard({
  title,
  value,
  icon: Icon,
  delta,
  trend = "up",
  deltaLabel = "vs mois précédent",
  progress,
}: KpiCardProps) {
  const TrendIcon = trend === "up" ? ArrowUp : ArrowDown;

  return (
    <section className="@container flex items-center gap-4 rounded-[14px] border border-simtis-border bg-simtis-card p-5 shadow-simtis">
      <span className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-simtis-light text-simtis-primary">
        <Icon className="h-6 w-6" aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm leading-snug text-simtis-text">{title}</p>
        {/* Un montant n'est jamais tronqué : sa taille suit la largeur de la carte (18px à 28px). */}
        <p className="mt-0.5 text-[length:clamp(18px,8.5cqw,28px)] leading-tight font-bold whitespace-nowrap text-simtis-primary tabular-nums">
          {value}
        </p>
        {delta && (
          <p className="mt-1 flex flex-wrap items-center gap-x-1.5 text-xs">
            <span
              className={cn(
                "inline-flex items-center gap-0.5 font-semibold",
                trend === "up" ? "text-simtis-success" : "text-simtis-danger",
              )}
            >
              <TrendIcon className="h-3.5 w-3.5" aria-hidden />
              {delta}
            </span>
            <span className="text-simtis-muted">{deltaLabel}</span>
          </p>
        )}
      </div>
      {progress !== undefined && <ProgressRing value={progress} />}
    </section>
  );
}

function ProgressRing({ value }: { value: number }) {
  const size = 64;
  const stroke = 7;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.min(100, Math.max(0, value));

  return (
    <div
      className="relative shrink-0"
      style={{ width: size, height: size }}
      role="img"
      aria-label={`${clamped} %`}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={stroke}
          className="stroke-simtis-light"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - clamped / 100)}
          className="stroke-simtis-primary"
        />
      </svg>
      <span className="absolute inset-0 grid place-items-center text-sm font-semibold text-simtis-text">
        {clamped}%
      </span>
    </div>
  );
}
