"use client";

import { TrendingUp } from "lucide-react";
import { useState, type ReactNode } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { BankLabel } from "@/components/banks/BankLabel";
import { Card } from "@/components/ui/Card";
import { formatDate } from "@/lib/balances";
import { cn } from "@/lib/cn";
import { formatAmount } from "@/lib/format";
import { JOURS_GRAPHIQUE, evolutionPoints, type EvolutionPoint } from "@/lib/position";
import type { BanqueColonne, JourBanques } from "@/types/position";

// Couleurs du design system : « Évolution de la position » = ligne chart-1, remplissage light
const LINE = "var(--simtis-chart-1)";
const FILL = "var(--simtis-light)";
const GRID = "var(--simtis-border)";
const MUTED = "var(--simtis-muted)";

type PositionChartProps = {
  jours: JourBanques[];
  /** Colonnes du tableau Banques : un bouton par banque qui a un compte courant MAD. */
  banques: BanqueColonne[];
};

/**
 * Courbe « facilité de caisse » des 30 derniers jours (mêmes chiffres que le tableau) : le TOTAL,
 * ou une banque à la fois (décision du 03/10/2026).
 */
export function PositionChart({ jours, banques }: PositionChartProps) {
  const [bankId, setBankId] = useState<number | null>(null);
  const choices = banques.filter((banque) => banque.bank_account_id !== null);
  const chosen = choices.find((banque) => banque.bank_id === bankId);
  const serie = chosen ? `Facilité de caisse ${chosen.code}` : "TOTAL facilité de caisse";
  const points = evolutionPoints(jours, JOURS_GRAPHIQUE, chosen ? chosen.bank_id : null);
  const known = points.filter((point) => point.totalText !== null);
  const negative = known.some((point) => point.totalText?.startsWith("-"));

  if (jours.length === 0) {
    return (
      <Card title="Évolution de la position" icon={TrendingUp}>
        <p className="text-sm text-simtis-muted">Aucun solde enregistré pour cette société.</p>
      </Card>
    );
  }

  return (
    <Card title="Évolution de la position" icon={TrendingUp}>
      {/* Une courbe à la fois : TOTAL ou une banque ; la rangée défile seule sur mobile */}
      <div
        className="mb-3 flex gap-2 overflow-x-auto pb-1"
        role="group"
        aria-label="Courbe affichée"
      >
        <SerieButton active={chosen === undefined} onClick={() => setBankId(null)}>
          TOTAL
        </SerieButton>
        {choices.map((banque) => (
          <SerieButton
            key={banque.bank_id}
            active={chosen?.bank_id === banque.bank_id}
            onClick={() => setBankId(banque.bank_id)}
          >
            <BankLabel code={banque.code} logo={banque.logo} />
          </SerieButton>
        ))}
      </div>
      <p className="mb-3 text-sm text-simtis-muted">
        {serie}, {points.length} derniers jours (DH)
      </p>
      {known.length === 0 ? (
        <p className="text-sm text-simtis-muted">Aucune valeur sur ces jours.</p>
      ) : (
        <>
          {/* Les chiffres détaillés sont dans le tableau Banques, juste au-dessus */}
          <div role="img" aria-label={summary(serie, points, known)} className="h-[260px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={points} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
                <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="label"
                  tick={{ fill: MUTED, fontSize: 12 }}
                  tickLine={false}
                  axisLine={{ stroke: GRID }}
                  minTickGap={16}
                />
                <YAxis
                  tickFormatter={(value: number) => formatAmount(value)}
                  tick={{ fill: MUTED, fontSize: 12 }}
                  tickLine={false}
                  axisLine={false}
                  width={92}
                />
                {negative && <ReferenceLine y={0} stroke={MUTED} />}
                <Tooltip
                  content={(props) => (
                    <ChartTooltip active={props.active} payload={props.payload} />
                  )}
                  cursor={{ stroke: MUTED, strokeDasharray: "3 3" }}
                />
                <Area
                  type="linear"
                  dataKey="total"
                  stroke={LINE}
                  strokeWidth={2}
                  fill={FILL}
                  fillOpacity={1}
                  // Un jour sans TOTAL reste un vide, jamais 0
                  connectNulls={false}
                  dot={false}
                  activeDot={{ r: 4, stroke: "var(--simtis-card)", strokeWidth: 2, fill: LINE }}
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </Card>
  );
}

function ChartTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: ReadonlyArray<{ payload?: unknown }>;
}) {
  const point = payload?.[0]?.payload as EvolutionPoint | undefined;
  if (!active || !point) return null;
  return (
    <div className="rounded-lg border border-simtis-border bg-simtis-card px-3 py-2 text-sm shadow-simtis">
      <p className="text-simtis-muted">{formatDate(point.date)}</p>
      <p className="font-semibold text-simtis-text tabular-nums">
        {formatAmount(point.totalText, "DH")}
      </p>
    </div>
  );
}

function SerieButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "shrink-0 rounded-[10px] border px-3 py-1.5 text-sm font-medium transition-colors duration-200",
        active
          ? "border-simtis-primary bg-simtis-light text-simtis-primary-dark"
          : "border-simtis-border bg-simtis-card text-simtis-text hover:bg-simtis-light/50",
      )}
    >
      {children}
    </button>
  );
}

/** Description du graphique pour les lecteurs d'écran. */
function summary(serie: string, points: EvolutionPoint[], known: EvolutionPoint[]) {
  const first = known[0];
  const last = known.at(-1) ?? first;
  return (
    `${serie} du ${formatDate(points[0].date)} au ` +
    `${formatDate(points.at(-1)?.date ?? null)} : de ${formatAmount(first.totalText, "DH")} ` +
    `à ${formatAmount(last.totalText, "DH")}.`
  );
}
