"use client";

import { Bell } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { useCompany } from "@/components/company/CompanyProvider";
import { PERMISSIONS, hasAnyPermission } from "@/lib/permissions";
import { getAlertes } from "@/services/dashboard";

/** Cloche de l'en-tête (P15, 14/10/2026) : nombre d'alertes du mois de la société active, lien
 * vers le dashboard. Sans la permission du dashboard, la cloche reste sans pastille. */
export function AlertBell() {
  const { user } = useAuth();
  const { company } = useCompany();
  const autorise = !!user && hasAnyPermission(user.permissions, [PERMISSIONS.DASHBOARD_VIEW]);
  const [compte, setCompte] = useState<{ cle: number; nombre: number } | null>(null);

  useEffect(() => {
    if (!autorise || !company) return;
    let cancelled = false;
    getAlertes(company.id).then(
      (result) => {
        if (!cancelled) setCompte({ cle: company.id, nombre: result.alertes.length });
      },
      () => undefined,
    );
    return () => {
      cancelled = true;
    };
  }, [autorise, company]);

  const nombre = compte && company && compte.cle === company.id ? compte.nombre : 0;
  return (
    <Link
      href="/dashboard"
      aria-label={nombre > 0 ? `${nombre} alerte${nombre > 1 ? "s" : ""}` : "Alertes"}
      className="relative grid h-10 w-10 place-items-center rounded-full border border-simtis-border bg-simtis-card text-simtis-text transition-colors duration-200 hover:bg-simtis-surface"
    >
      <Bell className="h-5 w-5" strokeWidth={1.75} aria-hidden />
      {nombre > 0 && (
        <span className="absolute -top-1 -right-1 grid h-[18px] min-w-[18px] place-items-center rounded-full bg-simtis-danger px-1 text-[10px] font-semibold text-white ring-2 ring-simtis-card">
          {nombre}
        </span>
      )}
    </Link>
  );
}
