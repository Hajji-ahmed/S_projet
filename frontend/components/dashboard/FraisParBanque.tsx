import { Landmark } from "lucide-react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card } from "@/components/ui/Card";
import { formatAmount } from "@/lib/format";
import type { Dashboard } from "@/types/dashboard";

/** Frais bancaires débités sur la période, par banque (comptes courants MAD, 19/10/2026). */
export function FraisParBanque({ data }: { data: Dashboard }) {
  const barres = data.banques
    .filter((banque) => banque.frais !== "0.00")
    // Recharts dessine des nombres : conversion pour l'affichage seulement
    .map((banque) => ({ code: banque.code, frais: banque.frais, valeur: Number(banque.frais) }));
  return (
    <Card title="Frais bancaires par banque" icon={Landmark}>
      {barres.length === 0 ? (
        <p className="text-sm text-simtis-muted">Aucun frais bancaire sur cette période.</p>
      ) : (
        <div className="h-[240px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={barres} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--simtis-border)" />
              <XAxis dataKey="code" tickLine={false} axisLine={false} fontSize={12} />
              <YAxis
                tickLine={false}
                axisLine={false}
                fontSize={11}
                width={70}
                tickFormatter={(valeur: number) => formatAmount(valeur)}
              />
              <Tooltip
                cursor={{ fill: "var(--simtis-surface)" }}
                formatter={(_value, _name, item) => [
                  formatAmount(item.payload.frais, "DH"),
                  "Frais",
                ]}
              />
              <Bar dataKey="valeur" fill="var(--simtis-chart-1)" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}
