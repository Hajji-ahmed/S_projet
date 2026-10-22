import {
  ArrowDown,
  ArrowRight,
  ArrowUp,
  Download,
  FileText,
  Landmark,
  Upload,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { Sparkline } from "@/components/dashboard/Sparkline";
import { cn } from "@/lib/cn";
import { formatVariation, tendance } from "@/lib/dashboard";
import { formatAmount } from "@/lib/format";
import type { Dashboard, Kpi } from "@/types/dashboard";

/** Les quatre cartes du haut : solde, encaissements, décaissements, transactions à rapprocher. */
export function KpiTiles({ data }: { data: Dashboard }) {
  const transactions = `${data.a_rapprocher} transaction${data.a_rapprocher > 1 ? "s" : ""}`;
  return (
    <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
      <Tuile
        titre="Solde total banques"
        icon={Landmark}
        pastille="bg-simtis-success-bg text-simtis-success-fg"
        valeur={data.solde_total.valeur ? formatAmount(data.solde_total.valeur, "DH") : "-"}
        courbe={
          <Sparkline
            valeurs={data.evolution.map((point) => point.solde)}
            couleur="var(--simtis-success)"
          />
        }
      >
        <p className="mb-1 text-xs text-simtis-muted">Comptes MAD (hors EUR / USD)</p>
        <Variation kpi={data.solde_total} />
      </Tuile>
      <Tuile
        titre="Encaissements"
        icon={Download}
        pastille="bg-simtis-info-bg text-simtis-info-fg"
        valeur={formatAmount(data.encaissements.valeur ?? "0", "DH")}
        courbe={
          <Sparkline
            valeurs={data.flux.map((jour) => jour.encaissements)}
            couleur="var(--simtis-info)"
          />
        }
      >
        <Variation kpi={data.encaissements} />
      </Tuile>
      <Tuile
        titre="Décaissements"
        icon={Upload}
        pastille="bg-simtis-danger-bg text-simtis-danger-fg"
        valeur={formatAmount(data.decaissements.valeur ?? "0", "DH")}
        courbe={
          <Sparkline
            valeurs={data.flux.map((jour) => jour.decaissements)}
            couleur="var(--simtis-danger)"
          />
        }
      >
        {/* Une hausse des décaissements n'est pas une bonne nouvelle : couleur inversée */}
        <Variation kpi={data.decaissements} inverse />
      </Tuile>
      <Tuile
        titre="Transactions à rapprocher"
        icon={FileText}
        pastille="bg-simtis-violet-bg text-simtis-violet-fg"
        valeur={transactions}
      >
        <Link
          href="/rapprochement"
          className="group inline-flex items-center gap-1 text-[13px] font-semibold text-simtis-orange-fg hover:underline"
        >
          Voir les détails
          <ArrowRight
            className="h-3.5 w-3.5 transition-transform duration-200 group-hover:translate-x-0.5"
            aria-hidden
          />
        </Link>
      </Tuile>
    </div>
  );
}

function Tuile({
  titre,
  icon: Icon,
  pastille,
  valeur,
  courbe,
  children,
}: {
  titre: string;
  icon: LucideIcon;
  /** Classes du carré pastel de l'icône. */
  pastille: string;
  valeur: string;
  courbe?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="@container flex gap-4 rounded-card border border-simtis-border bg-simtis-card p-5 shadow-simtis transition-shadow duration-200 hover:shadow-simtis-hover">
      <span className={cn("grid h-12 w-12 shrink-0 place-items-center rounded-[14px]", pastille)}>
        <Icon className="h-6 w-6" strokeWidth={1.75} aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <p className="pt-0.5 text-sm text-simtis-muted">{titre}</p>
          {courbe}
        </div>
        {/* Un montant n'est jamais tronqué : sa taille suit la largeur de la carte */}
        <p className="mt-0.5 text-[length:clamp(18px,8cqw,26px)] leading-tight font-bold tracking-tight whitespace-nowrap text-simtis-text tabular-nums">
          {valeur}
        </p>
        <div className="mt-2">{children}</div>
      </div>
    </section>
  );
}

function Variation({ kpi, inverse = false }: { kpi: Kpi; inverse?: boolean }) {
  const texte = formatVariation(kpi.variation);
  if (!texte) return <p className="text-xs text-simtis-muted">Pas de comparaison possible</p>;
  const hausse = tendance(kpi.variation) === "up";
  const bon = inverse ? !hausse : hausse;
  return (
    <p className="flex flex-wrap items-center gap-x-2 text-xs">
      <span
        className={cn(
          "inline-flex items-center gap-0.5 text-[13px] font-semibold tabular-nums",
          bon ? "text-simtis-success-fg" : "text-simtis-danger-fg",
        )}
      >
        {hausse ? (
          <ArrowUp className="h-3.5 w-3.5" aria-hidden />
        ) : (
          <ArrowDown className="h-3.5 w-3.5" aria-hidden />
        )}
        {texte}
      </span>
      <span className="text-simtis-muted">vs période précédente</span>
    </p>
  );
}
