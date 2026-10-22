"use client";

import { Activity, Building2, ListChecks } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { BankLabel } from "@/components/banks/BankLabel";
import { Petite } from "@/components/dashboard/SyntheseCards";
import { formatDateTime } from "@/lib/statements";
import { pourcentage } from "@/lib/dashboard";
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
      <ul className="divide-y divide-simtis-border text-sm">
        {lignes.map(([libelle, nombre]) => (
          <li key={libelle}>
            <Link
              href="/rapprochement"
              className="flex items-center justify-between gap-3 py-2 text-simtis-text hover:text-simtis-primary"
            >
              <span>{libelle}</span>
              <span
                className={
                  nombre > 0
                    ? "rounded-full bg-simtis-warning-bg px-2 py-0.5 text-xs font-semibold text-simtis-warning-fg tabular-nums"
                    : "text-xs text-simtis-muted tabular-nums"
                }
              >
                {nombre}
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

/** Les 10 dernières actions du journal d'audit (permission « audit.view »). */
export function ActiviteCard() {
  const [lignes, setLignes] = useState<LigneHistorique[] | null>(null);
  const [erreur, setErreur] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getHistorique({ page: 1, user_id: "", action: "", entite: "", from: "", to: "" }).then(
      (page) => {
        if (!cancelled) setLignes(page.items.slice(0, 10));
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
      lien={{ label: "Tout l'historique", href: "/historique" }}
    >
      {erreur && <p className="text-sm text-simtis-muted">Historique indisponible.</p>}
      {!erreur && lignes === null && <p className="text-sm text-simtis-muted">Chargement…</p>}
      {lignes !== null && lignes.length === 0 && (
        <p className="text-sm text-simtis-muted">Aucune action enregistrée.</p>
      )}
      {lignes !== null && lignes.length > 0 && (
        <ul className="divide-y divide-simtis-border text-[13px]">
          {lignes.map((ligne) => (
            <li key={ligne.id} className="flex flex-wrap items-baseline gap-x-2 py-1.5">
              <span className="font-medium text-simtis-text">{ligne.action_libelle}</span>
              <span className="text-simtis-muted">
                {ligne.utilisateur ?? "Système"} · {formatDateTime(ligne.created_at)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Petite>
  );
}
