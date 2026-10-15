import { Card } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { formatDate } from "@/lib/balances";
import { formatAmount } from "@/lib/format";
import { unite } from "@/lib/reconciliation";
import type { Dashboard } from "@/types/dashboard";
import type { Status } from "@/types/status";

/** Les cinq dernières opérations importées jusqu'à la fin de la période. */
export function DernieresCard({ data }: { data: Dashboard }) {
  return (
    <Card title="Dernières transactions" action={{ label: "Voir toutes", href: "/rapprochement" }}>
      {data.dernieres_operations.length === 0 ? (
        <p className="text-sm text-simtis-muted">Aucune opération importée.</p>
      ) : (
        <div className="-mx-1 overflow-x-auto">
          <table className="w-full min-w-[560px] text-[13.5px]">
            <thead className="bg-simtis-light/60 text-left text-[13px] text-simtis-primary-dark">
              <tr>
                <th className="rounded-l-[10px] px-3 py-2.5 font-semibold">Date</th>
                <th className="px-3 py-2.5 font-semibold">Libellé</th>
                <th className="px-3 py-2.5 text-right font-semibold">Débit</th>
                <th className="px-3 py-2.5 text-right font-semibold">Crédit</th>
                <th className="rounded-r-[10px] px-3 py-2.5 font-semibold">Statut</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-simtis-border">
              {data.dernieres_operations.map((op) => (
                <tr key={op.id} className="transition-colors duration-150 hover:bg-simtis-light/40">
                  <td className="px-3 py-3 whitespace-nowrap text-simtis-text tabular-nums">
                    {formatDate(op.date_operation)}
                  </td>
                  <td className="max-w-[280px] truncate px-3 py-3" title={op.libelle}>
                    <span className="text-simtis-muted">{op.bank_code} · </span>
                    {op.libelle}
                  </td>
                  <td className="px-3 py-3 text-right whitespace-nowrap text-simtis-text tabular-nums">
                    {formatAmount(op.debit, unite(op.devise), { dashForZero: true })}
                  </td>
                  <td className="px-3 py-3 text-right whitespace-nowrap text-simtis-text tabular-nums">
                    {formatAmount(op.credit, unite(op.devise), { dashForZero: true })}
                  </td>
                  <td className="px-3 py-3">
                    <StatusBadge status={op.statut as Status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
