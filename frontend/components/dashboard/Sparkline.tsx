import { Line, LineChart, ResponsiveContainer, YAxis } from "recharts";

/**
 * Petite courbe décorative d'une carte KPI, tracée sur une vraie série de la période. Les
 * montants arrivent en texte exact ; Number() ne sert qu'au dessin. Trait seul, calé sur le
 * minimum et le maximum de la série (27/10/2026 : remplie depuis 0, elle faisait un bloc plein).
 */
export function Sparkline({ valeurs, couleur }: { valeurs: (string | null)[]; couleur: string }) {
  const points = valeurs.map((valeur, index) => ({
    index,
    valeur: valeur === null ? null : Number(valeur),
  }));
  if (points.filter((point) => point.valeur !== null).length < 2) return null;
  return (
    <div className="h-8 w-20 shrink-0" aria-hidden>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 3, right: 2, bottom: 3, left: 2 }}>
          <YAxis hide domain={["dataMin", "dataMax"]} />
          <Line
            type="monotone"
            dataKey="valeur"
            stroke={couleur}
            strokeWidth={2}
            connectNulls
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
