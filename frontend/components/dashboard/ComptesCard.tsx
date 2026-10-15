import { ArrowDown, ArrowUp, ChevronRight, Landmark } from "lucide-react";
import Image from "next/image";
import Link from "next/link";

import { Card } from "@/components/ui/Card";
import { cn } from "@/lib/cn";
import { formatVariation, tendance } from "@/lib/dashboard";
import { formatAmount } from "@/lib/format";
import { unite } from "@/lib/reconciliation";
import type { CompteDashboard, Dashboard } from "@/types/dashboard";

/** Comptes actifs de la société : solde à la fin de la période, dans la devise du compte. */
export function ComptesCard({ data }: { data: Dashboard }) {
  return (
    <Card title="Comptes bancaires" action={{ label: "Voir tous", href: "/comptes" }}>
      {data.comptes.length === 0 ? (
        <p className="text-sm text-simtis-muted">Aucun compte actif pour cette société.</p>
      ) : (
        <ul className="-mx-2 divide-y divide-simtis-border">
          {data.comptes.map((compte) => (
            <Compte key={compte.id} compte={compte} />
          ))}
        </ul>
      )}
    </Card>
  );
}

function Compte({ compte }: { compte: CompteDashboard }) {
  const variation = formatVariation(compte.variation);
  const baisse = tendance(compte.variation) === "down";
  return (
    <li>
      <Link
        href={`/banques/${compte.bank_id}`}
        className="group flex items-center gap-3 rounded-[12px] px-2 py-3 transition-colors duration-150 hover:bg-simtis-surface"
      >
        <span className="grid h-10 w-10 shrink-0 place-items-center overflow-hidden rounded-full border border-simtis-border bg-simtis-card">
          {compte.bank_logo ? (
            <Image
              src={compte.bank_logo}
              alt=""
              width={28}
              height={28}
              className="h-7 w-7 object-contain"
            />
          ) : (
            <Landmark className="h-5 w-5 text-simtis-muted" aria-hidden />
          )}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-semibold text-simtis-text">
            {compte.bank_nom}
            {compte.devise !== "MAD" && (
              <span className="ml-1.5 rounded-full bg-simtis-info-bg px-1.5 py-0.5 text-[11px] font-medium text-simtis-info-fg">
                {compte.devise}
              </span>
            )}
          </span>
          <span className="block truncate text-xs text-simtis-muted tabular-nums">
            {compte.numero}
          </span>
        </span>
        <span className="text-right whitespace-nowrap">
          <span className="block text-sm font-semibold text-simtis-primary tabular-nums">
            {compte.solde ? formatAmount(compte.solde, unite(compte.devise)) : "-"}
          </span>
          {variation && (
            <span
              className={cn(
                "inline-flex items-center gap-0.5 text-xs font-semibold tabular-nums",
                baisse ? "text-simtis-danger-fg" : "text-simtis-success-fg",
              )}
            >
              {baisse ? (
                <ArrowDown className="h-3 w-3" aria-hidden />
              ) : (
                <ArrowUp className="h-3 w-3" aria-hidden />
              )}
              {variation}
            </span>
          )}
        </span>
        <ChevronRight
          className="h-4 w-4 shrink-0 text-simtis-muted transition-transform duration-200 group-hover:translate-x-0.5"
          aria-hidden
        />
      </Link>
    </li>
  );
}
