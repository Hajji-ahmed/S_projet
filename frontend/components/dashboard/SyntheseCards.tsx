import {
  ArrowRight,
  Bell,
  CircleAlert,
  CircleCheck,
  FileText,
  Info,
  RefreshCw,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";
import { pourcentage } from "@/lib/dashboard";
import type { Alerte, Dashboard } from "@/types/dashboard";

/** Avancement du rapprochement de la période (onglet « Suivi »). */
export function RapprochementCard({ data }: { data: Dashboard }) {
  return (
    <Petite
      titre="Rapprochement bancaire"
      icon={RefreshCw}
      pastille="bg-simtis-success-bg text-simtis-success-fg"
      lien={{ label: "Voir le détail", href: "/rapprochement" }}
      centre
    >
      <Anneau
        pourcent={pourcentage(data.rapprochees, data.total_operations)}
        couleur="stroke-simtis-success"
        valeurs={[
          [data.rapprochees, "rapprochées", "bg-simtis-success"],
          [data.a_rapprocher, "à rapprocher", "bg-simtis-warning"],
          [data.total_operations, "total", "bg-simtis-chart-4"],
        ]}
      />
    </Petite>
  );
}

/** Écritures de frais SIMTIS exportées / à exporter (onglet « Suivi »). */
export function EcrituresCard({ data }: { data: Dashboard }) {
  const totalEcritures = data.ecritures_exportees + data.ecritures_a_exporter;
  return (
    <Petite
      titre="Écritures comptables"
      icon={FileText}
      pastille="bg-simtis-violet-bg text-simtis-violet-fg"
      lien={{ label: "Voir les écritures", href: "/ecritures" }}
      centre
    >
      <Anneau
        pourcent={pourcentage(data.ecritures_exportees, totalEcritures)}
        couleur="stroke-simtis-info"
        valeurs={[
          [data.ecritures_exportees, "exportées", "bg-simtis-info"],
          [data.ecritures_a_exporter, "à exporter", "bg-simtis-secondary"],
          [totalEcritures, "total", "bg-simtis-chart-4"],
        ]}
      />
    </Petite>
  );
}

export function Petite({
  titre,
  icon: Icon,
  pastille,
  lien,
  badge,
  className,
  centre = false,
  children,
}: {
  titre: string;
  icon: LucideIcon;
  pastille: string;
  lien?: { label: string; href: string };
  badge?: ReactNode;
  className?: string;
  /** Contenu centré en hauteur (anneaux, 27/10/2026). */
  centre?: boolean;
  children: ReactNode;
}) {
  return (
    <section
      className={cn(
        "flex flex-col rounded-card border border-simtis-border bg-simtis-card p-5 shadow-simtis",
        className,
      )}
    >
      <header className="mb-4 flex items-center gap-3">
        <span className={cn("grid h-9 w-9 shrink-0 place-items-center rounded-[10px]", pastille)}>
          <Icon className="h-[18px] w-[18px]" strokeWidth={1.75} aria-hidden />
        </span>
        <h2 className="min-w-0 flex-1 text-[15px] font-semibold tracking-tight text-simtis-text">
          {titre}
        </h2>
        {badge}
      </header>
      <div className={cn("flex-1", centre && "flex flex-col justify-center")}>{children}</div>
      {lien && (
        <Link
          href={lien.href}
          className="group mt-3 inline-flex items-center gap-1 self-end text-[13px] font-medium text-simtis-primary hover:text-simtis-primary-dark"
        >
          {lien.label}
          <ArrowRight
            className="h-3.5 w-3.5 transition-transform duration-200 group-hover:translate-x-0.5"
            aria-hidden
          />
        </Link>
      )}
    </section>
  );
}

/** Anneau de progression en SVG, avec ses trois chiffres à droite. */
function Anneau({
  pourcent,
  couleur,
  valeurs,
}: {
  pourcent: number;
  /** Classe de trait de la partie remplie (stroke-simtis-…). */
  couleur: string;
  valeurs: [number, string, string][];
}) {
  const taille = 104;
  const trait = 11;
  const rayon = (taille - trait) / 2;
  const circonference = 2 * Math.PI * rayon;
  return (
    <div className="flex items-center gap-5">
      <div
        className="relative shrink-0"
        style={{ width: taille, height: taille }}
        role="img"
        aria-label={`${pourcent} %`}
      >
        <svg
          width={taille}
          height={taille}
          viewBox={`0 0 ${taille} ${taille}`}
          className="-rotate-90"
        >
          <circle
            cx={taille / 2}
            cy={taille / 2}
            r={rayon}
            fill="none"
            strokeWidth={trait}
            className="stroke-simtis-surface"
          />
          <circle
            cx={taille / 2}
            cy={taille / 2}
            r={rayon}
            fill="none"
            strokeWidth={trait}
            strokeLinecap="round"
            strokeDasharray={circonference}
            strokeDashoffset={circonference * (1 - Math.min(pourcent, 100) / 100)}
            className={couleur}
          />
        </svg>
        <span className="absolute inset-0 grid place-items-center text-xl font-bold tracking-tight text-simtis-text tabular-nums">
          {pourcent}%
        </span>
      </div>
      <ul className="min-w-0 flex-1 space-y-2 text-[13px]">
        {valeurs.map(([valeur, libelle, puce]) => (
          <li key={libelle} className="flex items-center gap-2">
            <span className={cn("h-2.5 w-2.5 shrink-0 rounded-full", puce)} aria-hidden />
            <span className="truncate text-simtis-muted">{libelle}</span>
            <span className="ml-auto font-semibold text-simtis-text tabular-nums">{valeur}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export const PUCES: Record<Alerte["niveau"], string> = {
  danger: "bg-simtis-danger",
  warning: "bg-simtis-warning",
  info: "bg-simtis-info",
};

// Alertes du dashboard (27/10/2026) : une ligne colorée par niveau, avec son icône
const STYLES_ALERTE: Record<Alerte["niveau"], { fond: string; icone: LucideIcon }> = {
  danger: { fond: "bg-simtis-danger-bg text-simtis-danger-fg", icone: TriangleAlert },
  warning: { fond: "bg-simtis-warning-bg text-simtis-warning-fg", icone: CircleAlert },
  info: { fond: "bg-simtis-info-bg text-simtis-info-fg", icone: Info },
};

/** « 797 opérations à rapprocher » → le nombre en gras, le reste en texte. */
function MessageAlerte({ message }: { message: string }) {
  const nombre = /^([\d\s\u202f.,]+)(\s.*)$/.exec(message);
  if (!nombre) return <>{message}</>;
  return (
    <>
      <strong className="font-semibold tabular-nums">{nombre[1].trim()}</strong>
      {nombre[2]}
    </>
  );
}

export function Alertes({ alertes }: { alertes: Alerte[] }) {
  return (
    <Petite
      titre="Alertes et notifications"
      icon={Bell}
      pastille="bg-simtis-orange-bg text-simtis-orange-fg"
      badge={
        alertes.length > 0 && (
          <span className="grid h-6 min-w-6 place-items-center rounded-full bg-simtis-danger px-1.5 text-xs font-semibold text-white">
            {alertes.length}
          </span>
        )
      }
    >
      {/* La cloche de l'en-tête compte le mois en cours : ce chiffre peut donc différer */}
      <p className="mb-2 text-xs text-simtis-muted">Période et banque choisies</p>
      {alertes.length === 0 ? (
        <p className="flex items-center gap-2 rounded-[10px] bg-simtis-success-bg px-3 py-2.5 text-sm text-simtis-success-fg">
          <CircleCheck className="h-4 w-4 shrink-0" aria-hidden />
          Aucune alerte sur cette période.
        </p>
      ) : (
        <ul className="space-y-2 text-[13px]">
          {alertes.map((alerte) => {
            const { fond, icone: Icone } = STYLES_ALERTE[alerte.niveau];
            return (
              <li key={alerte.message}>
                <Link
                  href={alerte.lien}
                  className={cn(
                    "group flex items-center gap-3 rounded-[10px] px-3 py-2.5 transition-shadow duration-150 hover:shadow-simtis",
                    fond,
                  )}
                >
                  <Icone className="h-4 w-4 shrink-0" aria-hidden />
                  <span className="min-w-0 flex-1 truncate text-simtis-text" title={alerte.message}>
                    <MessageAlerte message={alerte.message} />
                  </span>
                  <span className="inline-flex shrink-0 items-center gap-1 text-xs font-semibold">
                    Traiter
                    <ArrowRight
                      className="h-3.5 w-3.5 transition-transform duration-200 group-hover:translate-x-0.5"
                      aria-hidden
                    />
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </Petite>
  );
}
