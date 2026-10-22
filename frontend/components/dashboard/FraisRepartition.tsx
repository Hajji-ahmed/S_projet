import { Receipt } from "lucide-react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { Card } from "@/components/ui/Card";
import { partFrais } from "@/lib/dashboard";
import { formatAmount, formatCompact } from "@/lib/format";
import type { Dashboard } from "@/types/dashboard";

// Couleurs des catégories : tokens du design system uniquement
const COULEURS = [
  "var(--simtis-chart-1)",
  "var(--simtis-chart-2)",
  "var(--simtis-warning)",
  "var(--simtis-info)",
  "var(--simtis-danger)",
  "var(--simtis-chart-4)",
];

/** Frais bancaires débités sur la période (comptes courants MAD), par catégorie. */
export function FraisRepartition({ data }: { data: Dashboard }) {
  const secteurs = data.frais.map((item, index) => ({
    ...item,
    // Recharts dessine des nombres : conversion pour l'affichage seulement
    valeur: Number(item.total),
    couleur: COULEURS[index % COULEURS.length],
  }));
  return (
    <Card title="Répartition des frais bancaires" icon={Receipt}>
      {secteurs.length === 0 ? (
        <p className="text-sm text-simtis-muted">Aucun frais bancaire sur cette période.</p>
      ) : (
        <div className="flex flex-col items-center gap-5 sm:flex-row">
          <div className="relative h-[176px] w-[176px] shrink-0">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Tooltip
                  formatter={(_value, _name, item) => [
                    formatAmount(item.payload.total, "DH"),
                    item.payload.libelle,
                  ]}
                />
                <Pie
                  data={secteurs}
                  dataKey="valeur"
                  nameKey="libelle"
                  innerRadius={60}
                  outerRadius={86}
                  paddingAngle={secteurs.length > 1 ? 2 : 0}
                  cornerRadius={4}
                  stroke="none"
                  isAnimationActive={false}
                >
                  {secteurs.map((item) => (
                    <Cell key={item.code} fill={item.couleur} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 grid place-items-center text-center">
              <div>
                {/* Format court : le montant exact déborderait du cercle (21/10/2026) */}
                <p
                  className="text-[15px] font-bold tracking-tight whitespace-nowrap text-simtis-text tabular-nums"
                  title={formatAmount(data.frais_total, "DH")}
                >
                  {formatCompact(data.frais_total, "DH")}
                </p>
                <p className="text-xs text-simtis-muted">Total des frais</p>
              </div>
            </div>
          </div>
          <ul className="w-full min-w-0 space-y-2.5 text-sm">
            {secteurs.map((item) => (
              <li key={item.code} className="flex items-center gap-2.5">
                <span
                  className="h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{ background: item.couleur }}
                  aria-hidden
                />
                <span className="min-w-0 flex-1 truncate text-simtis-text" title={item.libelle}>
                  {item.libelle}
                </span>
                <span className="w-16 shrink-0 text-right font-semibold whitespace-nowrap tabular-nums">
                  {partFrais(item.total, data.frais_total)} %
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}
