import { Landmark } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card } from "@/components/ui/Card";
import { formatAmount, formatCompact } from "@/lib/format";
import type { Dashboard } from "@/types/dashboard";

/** Frais bancaires débités sur la période, par banque (comptes courants MAD, 19/10/2026). */
export function FraisParBanque({ data }: { data: Dashboard }) {
  const barres = data.banques
    .filter((banque) => banque.frais !== "0.00")
    // Recharts dessine des nombres : conversion pour l'affichage seulement
    .map((banque) => ({
      code: banque.code,
      logo: banque.logo,
      frais: banque.frais,
      valeur: Number(banque.frais),
    }));
  const logos = new Map(barres.map((barre) => [barre.code, barre.logo]));
  return (
    <Card title="Frais bancaires par banque" icon={Landmark}>
      {barres.length === 0 ? (
        <p className="text-sm text-simtis-muted">Aucun frais bancaire sur cette période.</p>
      ) : (
        <div className="h-[240px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={barres} margin={{ top: 24, right: 8, left: 8, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--simtis-border)" />
              <XAxis
                dataKey="code"
                tickLine={false}
                axisLine={false}
                height={44}
                interval={0}
                tick={({ x, y, payload }) => (
                  <LogoBanque x={x} y={y} code={payload.value} logo={logos.get(payload.value)} />
                )}
              />
              <YAxis
                tickLine={false}
                axisLine={false}
                fontSize={11}
                width={70}
                tickFormatter={(valeur: number) => formatCompact(valeur)}
              />
              <Tooltip
                cursor={{ fill: "var(--simtis-surface)" }}
                formatter={(_value, _name, item) => [
                  formatAmount(item.payload.frais, "DH"),
                  "Frais",
                ]}
              />
              <Bar
                dataKey="valeur"
                fill="var(--simtis-chart-1)"
                radius={[6, 6, 0, 0]}
                maxBarSize={56}
                isAnimationActive={false}
              >
                {/* Montant au-dessus de chaque barre (format court, exact dans l'info-bulle) */}
                <LabelList
                  dataKey="valeur"
                  position="top"
                  formatter={(valeur) => formatCompact(Number(valeur), "DH")}
                  fill="var(--simtis-text)"
                  fontSize={12}
                  fontWeight={600}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}

/** Logo et code d'une banque sous sa barre (SVG : Recharts dessine l'axe dans le graphique). */
function LogoBanque({
  x,
  y,
  code,
  logo,
}: {
  x: number | string;
  y: number | string;
  code: string;
  logo: string | null | undefined;
}) {
  const cx = Number(x);
  const cy = Number(y);
  return (
    <g>
      {logo && <image href={logo} x={cx - 9} y={cy + 2} width={18} height={18} />}
      <text
        x={cx}
        y={cy + (logo ? 34 : 14)}
        textAnchor="middle"
        fontSize={12}
        fill="var(--simtis-muted)"
      >
        {code}
      </text>
    </g>
  );
}
