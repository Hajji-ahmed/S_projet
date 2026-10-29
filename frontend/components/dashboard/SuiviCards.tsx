"use client";

import {
  Activity,
  ArrowLeftRight,
  Building2,
  FileUp,
  KeyRound,
  ListChecks,
  Receipt,
  Settings,
  Trash2,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { BankLabel } from "@/components/banks/BankLabel";
import { Petite } from "@/components/dashboard/SyntheseCards";
import { cn } from "@/lib/cn";
import { heureRelative, pourcentage } from "@/lib/dashboard";
import { formatDateTime } from "@/lib/statements";
import { getHistorique } from "@/services/historique";
import type { Dashboard } from "@/types/dashboard";
import type { LigneHistorique } from "@/types/historique";

/** Travail en attente, chaque compteur menant à l'écran où il se traite (19/10/2026). */
export function TachesCard({ data }: { data: Dashboard }) {
  const t = data.taches;
  const lignes: [string, number][] = [
    ["Propositions fortes à valider", t.propositions_fortes],
    ["Propositions à vérifier", t.propositions_a_verifier],
    ["Opérations ambiguës", t.operations_ambigues],
    ["Écritures ambiguës", t.ecritures_ambigues],
    ["Frais bancaires à comptabiliser", t.a_comptabiliser],
    ["Écritures de frais à exporter pour Sage", t.a_exporter],
  ];
  return (
    <Petite
      titre="Tâches en attente"
      icon={ListChecks}
      pastille="bg-simtis-light text-simtis-primary"
    >
      {/* Une tuile par tâche (27/10/2026) : orange s'il reste du travail, grisée à 0 */}
      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {lignes.map(([libelle, nombre]) => (
          <li key={libelle}>
            <Link
              href="/rapprochement"
              className={cn(
                "flex h-full flex-col justify-between gap-2 rounded-[12px] border p-3 transition-shadow duration-150 hover:shadow-simtis",
                nombre > 0
                  ? "border-transparent bg-simtis-warning-bg"
                  : "border-simtis-border bg-simtis-surface",
              )}
            >
              <span
                className={cn(
                  "text-2xl leading-none font-bold tracking-tight tabular-nums",
                  nombre > 0 ? "text-simtis-warning-fg" : "text-simtis-muted",
                )}
              >
                {nombre}
              </span>
              <span
                className={cn(
                  "text-xs leading-snug",
                  nombre > 0 ? "text-simtis-text" : "text-simtis-muted",
                )}
              >
                {libelle}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </Petite>
  );
}

/** Taux de rapprochement de chaque banque sur la période. */
export function BanquesCard({ data, className }: { data: Dashboard; className?: string }) {
  return (
    <Petite
      className={className}
      titre="Rapprochement par banque"
      icon={Building2}
      pastille="bg-simtis-info-bg text-simtis-info-fg"
    >
      {data.banques.length === 0 ? (
        <p className="text-sm text-simtis-muted">Aucune opération sur cette période.</p>
      ) : (
        <ul className="space-y-3">
          {data.banques.map((banque) => {
            const pourcent = pourcentage(banque.rapprochees, banque.total);
            return (
              <li key={banque.code} className="space-y-1">
                <div className="flex items-center justify-between gap-3 text-sm">
                  <BankLabel code={banque.code} logo={banque.logo} />
                  <span className="text-xs text-simtis-muted tabular-nums">
                    {banque.rapprochees} / {banque.total} ·{" "}
                    <strong className="text-simtis-text">{pourcent} %</strong>
                  </span>
                </div>
                <div
                  className="h-2 overflow-hidden rounded-full bg-simtis-surface"
                  role="progressbar"
                  aria-label={`Rapprochement ${banque.code}`}
                  aria-valuenow={pourcent}
                  aria-valuemin={0}
                  aria-valuemax={100}
                >
                  <div
                    className="h-full rounded-full bg-simtis-success transition-[width] duration-200"
                    style={{ width: `${pourcent}%` }}
                  />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Petite>
  );
}

// Icône d'une action du journal, d'après son code (27/10/2026) ; Activity par défaut
const ICONES_ACTION: [RegExp, LucideIcon][] = [
  [/connexion|deconnexion|mot_de_passe/, KeyRound],
  [/suppression/, Trash2],
  [/import|export/, FileUp],
  [/frais|comptabilisation/, Receipt],
  [/rapprochement|rejet|validation|reprise/, ArrowLeftRight],
  [/parametre|permission|role|utilisateur/, Settings],
];

function iconeAction(action: string): LucideIcon {
  return ICONES_ACTION.find(([motif]) => motif.test(action))?.[1] ?? Activity;
}

/** Les 5 dernières actions du journal d'audit (permission « audit.view »). */
export function ActiviteCard() {
  const [lignes, setLignes] = useState<LigneHistorique[] | null>(null);
  const [erreur, setErreur] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getHistorique({ page: 1, user_id: "", action: "", entite: "", from: "", to: "" }).then(
      (page) => {
        if (!cancelled) setLignes(page.items.slice(0, 5));
      },
      () => {
        if (!cancelled) setErreur(true);
      },
    );
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Petite
      titre="Activité récente"
      icon={Activity}
      pastille="bg-simtis-violet-bg text-simtis-violet-fg"
      lien={{ label: "Voir l'historique", href: "/historique" }}
    >
      {erreur && <p className="text-sm text-simtis-muted">Historique indisponible.</p>}
      {!erreur && lignes === null && <p className="text-sm text-simtis-muted">Chargement…</p>}
      {lignes !== null && lignes.length === 0 && (
        <p className="text-sm text-simtis-muted">Aucune action enregistrée.</p>
      )}
      {lignes !== null && lignes.length > 0 && (
        <ol className="relative space-y-3 text-[13px]">
          {/* Frise : un trait vertical relie les actions */}
          <span className="absolute top-2 bottom-2 left-[13px] w-px bg-simtis-border" aria-hidden />
          {lignes.map((ligne) => {
            const Icone = iconeAction(ligne.action);
            return (
              <li key={ligne.id} className="relative flex items-start gap-3">
                <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full border border-simtis-border bg-simtis-card text-simtis-primary">
                  <Icone className="h-3.5 w-3.5" aria-hidden />
                </span>
                <span className="min-w-0 flex-1 pt-1">
                  <span className="block truncate font-medium text-simtis-text">
                    {ligne.action_libelle}
                  </span>
                  <span className="block truncate text-xs text-simtis-muted">
                    {ligne.utilisateur ?? "Système"}
                  </span>
                </span>
                <time
                  dateTime={ligne.created_at}
                  title={formatDateTime(ligne.created_at)}
                  className="shrink-0 pt-1 text-xs whitespace-nowrap text-simtis-muted"
                >
                  {heureRelative(ligne.created_at)}
                </time>
              </li>
            );
          })}
        </ol>
      )}
    </Petite>
  );
}
