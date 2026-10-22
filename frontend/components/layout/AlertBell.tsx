"use client";

import { Bell, ChevronRight } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { useCompany } from "@/components/company/CompanyProvider";
import { PUCES } from "@/components/dashboard/SyntheseCards";
import { cn } from "@/lib/cn";
import { PERMISSIONS, hasAnyPermission } from "@/lib/permissions";
import { getAlertes } from "@/services/dashboard";
import type { Alerte } from "@/types/dashboard";

/** Cloche de l'en-tête (P15, 14/10/2026) : alertes du mois en cours de la société active.
 *
 * Depuis le 21/10/2026, un clic ouvre un panneau qui les liste, et elles sont rechargées à chaque
 * changement de page et à chaque ouverture (l'en-tête reste monté d'une page à l'autre, le badge
 * gardait sinon le chiffre du premier chargement). Même calcul que le dashboard, mais toujours sur
 * le mois en cours. Sans la permission du dashboard, la cloche reste sans pastille. */
export function AlertBell() {
  const { user } = useAuth();
  const { company } = useCompany();
  const pathname = usePathname();
  const autorise = !!user && hasAnyPermission(user.permissions, [PERMISSIONS.DASHBOARD_VIEW]);
  const [resultat, setResultat] = useState<{ cle: number; alertes: Alerte[] } | null>(null);
  // Page sur laquelle le panneau a été ouvert : il se ferme dès qu'on change de page
  const [ouvertSur, setOuvertSur] = useState<string | null>(null);
  const [ouvertures, setOuvertures] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const ouvert = ouvertSur === pathname;

  useEffect(() => {
    if (!autorise || !company) return;
    let cancelled = false;
    getAlertes(company.id).then(
      (result) => {
        if (!cancelled) setResultat({ cle: company.id, alertes: result.alertes });
      },
      () => undefined,
    );
    return () => {
      cancelled = true;
    };
  }, [autorise, company, pathname, ouvertures]);

  useEffect(() => {
    if (!ouvert) return;
    const fermerSurEchap = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOuvertSur(null);
    };
    const fermerSurClicExterieur = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOuvertSur(null);
    };
    window.addEventListener("keydown", fermerSurEchap);
    window.addEventListener("mousedown", fermerSurClicExterieur);
    return () => {
      window.removeEventListener("keydown", fermerSurEchap);
      window.removeEventListener("mousedown", fermerSurClicExterieur);
    };
  }, [ouvert]);

  const alertes = resultat && company && resultat.cle === company.id ? resultat.alertes : [];
  const nombre = alertes.length;

  function basculer() {
    if (ouvert) {
      setOuvertSur(null);
    } else {
      setOuvertSur(pathname);
      setOuvertures((n) => n + 1);
    }
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={basculer}
        aria-haspopup="dialog"
        aria-expanded={ouvert}
        aria-label={nombre > 0 ? `${nombre} alerte${nombre > 1 ? "s" : ""}` : "Alertes"}
        className="relative grid h-10 w-10 place-items-center rounded-full border border-simtis-border bg-simtis-card text-simtis-text transition-colors duration-200 hover:bg-simtis-surface"
      >
        <Bell className="h-5 w-5" strokeWidth={1.75} aria-hidden />
        {nombre > 0 && (
          <span className="absolute -top-1 -right-1 grid h-[18px] min-w-[18px] place-items-center rounded-full bg-simtis-danger px-1 text-[10px] font-semibold text-white ring-2 ring-simtis-card">
            {nombre}
          </span>
        )}
      </button>

      {ouvert && (
        <div
          role="dialog"
          aria-label="Alertes du mois en cours"
          className="absolute right-0 z-30 mt-2 w-[min(22rem,calc(100vw-2rem))] rounded-card border border-simtis-border bg-simtis-card p-2 shadow-simtis-hover"
        >
          <div className="px-3 py-2">
            <p className="text-sm font-semibold text-simtis-text">Alertes</p>
            <p className="text-xs text-simtis-muted">Mois en cours · {company?.nom}</p>
          </div>
          <div className="my-1 border-t border-simtis-border" />
          {!autorise ? (
            <p className="px-3 py-2 text-sm text-simtis-muted">
              Les alertes demandent l&apos;accès au dashboard.
            </p>
          ) : nombre === 0 ? (
            <p className="px-3 py-2 text-sm text-simtis-muted">Aucune alerte ce mois-ci.</p>
          ) : (
            <ul className="max-h-80 overflow-y-auto">
              {alertes.map((alerte) => (
                <li key={alerte.message}>
                  <Link
                    href={alerte.lien}
                    onClick={() => setOuvertSur(null)}
                    className="flex items-center gap-2.5 rounded-[10px] px-3 py-2 text-[13px] text-simtis-text transition-colors hover:bg-simtis-surface"
                  >
                    <span
                      className={cn("h-2 w-2 shrink-0 rounded-full", PUCES[alerte.niveau])}
                      aria-hidden
                    />
                    <span className="min-w-0 flex-1">{alerte.message}</span>
                    <ChevronRight className="h-4 w-4 shrink-0 text-simtis-muted" aria-hidden />
                  </Link>
                </li>
              ))}
            </ul>
          )}
          {autorise && (
            <>
              <div className="my-1 border-t border-simtis-border" />
              <Link
                href="/dashboard"
                onClick={() => setOuvertSur(null)}
                className="block rounded-[10px] px-3 py-2 text-sm font-medium text-simtis-primary transition-colors hover:bg-simtis-surface"
              >
                Voir le dashboard
              </Link>
            </>
          )}
        </div>
      )}
    </div>
  );
}
