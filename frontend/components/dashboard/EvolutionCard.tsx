import { TrendingUp } from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card } from "@/components/ui/Card";
import { formatDate } from "@/lib/balances";
import { jourCourt } from "@/lib/dashboard";
import { formatAmount, formatCompact } from "@/lib/format";
import type { Dashboard } from "@/types/dashboard";

// Couleurs des graphiques : tokens du design system uniquement
const SOLDE = "var(--simtis-secondary)";
const GRILLE = "var(--simtis-border)";
const GRIS = "var(--simtis-muted)";

function axe(value: number): string {
  return formatCompact(value);
}

/** Solde total des comptes courants MAD, jour par jour (dernier solde connu de chaque compte). */
export function EvolutionCard({ data }: { data: Dashboard }) {
  const points = data.evolution.map((point) => ({
    date: point.date,
    jour: jourCourt(point.date),
    // Recharts dessine des nombres : conversion pour l'affichage seulement
    solde: point.solde === null ? null : Number(point.solde),
    texte: point.solde,
  }));
  const connus = points.some((point) => point.solde !== null);
  return (
    <Card title="Évolution des soldes bancaires" icon={TrendingUp}>
      {!connus ? (
        <p className="text-sm text-simtis-muted">Aucun solde connu sur cette période.</p>
      ) : (
        <>
          <div className="h-[250px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid stroke={GRILLE} vertical={false} />
                <XAxis
                  dataKey="jour"
                  tick={{ fill: GRIS, fontSize: 12 }}
                  tickLine={false}
                  axisLine={{ stroke: GRILLE }}
                  minTickGap={24}
                />
                <YAxis
                  tick={{ fill: GRIS, fontSize: 12 }}
                  tickLine={false}
                  axisLine={false}
                  width={72}
                  tickFormatter={axe}
                />
                <Tooltip
                  cursor={{ stroke: GRIS, strokeDasharray: "3 3" }}
                  labelFormatter={(_label, items) =>
                    items[0] ? formatDate(items[0].payload.date) : ""
                  }
                  formatter={(_value, _name, item) => [
                    formatAmount(item.payload.texte, "DH"),
                    "Solde réel",
                  ]}
                />
                <Area
                  type="monotone"
                  dataKey="solde"
                  stroke={SOLDE}
                  strokeWidth={2.5}
                  fill={SOLDE}
                  fillOpacity={0.14}
                  dot={{ r: 3, fill: SOLDE, stroke: "var(--simtis-card)", strokeWidth: 1.5 }}
                  activeDot={{ r: 5, fill: SOLDE, stroke: "var(--simtis-card)", strokeWidth: 2 }}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-3 flex flex-wrap items-center justify-center gap-x-5 gap-y-1 text-xs text-simtis-muted">
            <span className="flex items-center gap-2 text-simtis-text">
              <span className="h-2.5 w-2.5 rounded-full bg-simtis-secondary" aria-hidden />
              Solde réel
            </span>
            <span>Le solde prévisionnel viendra avec la phase Prévisions</span>
          </p>
        </>
      )}
    </Card>
  );
}
