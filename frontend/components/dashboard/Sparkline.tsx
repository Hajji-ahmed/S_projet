import { Area, AreaChart, ResponsiveContainer } from "recharts";

/**
 * Petite courbe décorative d'une carte KPI, tracée sur une vraie série de la période. Les
 * montants arrivent en texte exact ; Number() ne sert qu'au dessin.
 */
export function Sparkline({ valeurs, couleur }: { valeurs: (string | null)[]; couleur: string }) {
  const points = valeurs.map((valeur, index) => ({
    index,
    valeur: valeur === null ? null : Number(valeur),
  }));
  if (points.filter((point) => point.valeur !== null).length < 2) return null;
  return (
    <div className="h-9 w-20 shrink-0" aria-hidden>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={points} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
          <Area
            type="monotone"
            dataKey="valeur"
            stroke={couleur}
            strokeWidth={1.75}
            fill={couleur}
            fillOpacity={0.14}
            connectNulls
            dot={false}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
