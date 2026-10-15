"use client";

import { useEffect, useState } from "react";

import { ComptesCard } from "@/components/dashboard/ComptesCard";
import { DernieresCard } from "@/components/dashboard/DernieresCard";
import { EvolutionCard } from "@/components/dashboard/EvolutionCard";
import { FraisRepartition } from "@/components/dashboard/FraisRepartition";
import { KpiTiles } from "@/components/dashboard/KpiTiles";
import { PeriodePicker } from "@/components/dashboard/PeriodePicker";
import { SyntheseCards } from "@/components/dashboard/SyntheseCards";
import { useCompany } from "@/components/company/CompanyProvider";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState, Skeleton } from "@/components/ui/LoadingState";
import { PageHeader } from "@/components/ui/PageHeader";
import { businessToday } from "@/lib/balances";
import { moisEnCours } from "@/lib/dashboard";
import { getDashboard } from "@/services/dashboard";
import type { Dashboard } from "@/types/dashboard";

/**
 * Dashboard (P15) : la vue d'ensemble de la société active sur une période (le mois en cours par
 * défaut), disposée comme la maquette du métier. Tous les chiffres viennent de l'API
 * (`GET /api/dashboard`) ; les totaux ne portent que sur les comptes courants MAD.
 */
export function DashboardView() {
  const { company } = useCompany();
  return company ? <DashboardSociete key={company.id} companyId={company.id} /> : null;
}

function DashboardSociete({ companyId }: { companyId: number }) {
  const [periode, setPeriode] = useState(() => moisEnCours(businessToday()));
  const [data, setData] = useState<Dashboard | null>(null);
  const [state, setState] = useState<"loading" | "error" | "ready">("loading");
  const [retry, setRetry] = useState(0);
  const valide = periode.from !== "" && periode.to !== "" && periode.from <= periode.to;

  useEffect(() => {
    if (!valide) return;
    let cancelled = false;
    getDashboard(companyId, periode.from, periode.to).then(
      (result) => {
        if (cancelled) return;
        setData(result);
        setState("ready");
      },
      () => {
        if (!cancelled) setState("error");
      },
    );
    return () => {
      cancelled = true;
    };
  }, [companyId, periode, valide, retry]);

  function changer(cle: "from" | "to", valeur: string) {
    setState("loading");
    setPeriode((courante) => ({ ...courante, [cle]: valeur }));
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description="Vue d'ensemble de la position bancaire, du rapprochement et des prévisions"
        actions={<PeriodePicker periode={periode} onChange={changer} />}
      />

      {!valide && (
        <p className="text-sm text-simtis-danger-fg">
          La date de début doit précéder la date de fin.
        </p>
      )}
      {valide && state === "error" && (
        <Card>
          <ErrorState
            message="Impossible de charger le dashboard."
            onRetry={() => {
              setState("loading");
              setRetry((n) => n + 1);
            }}
          />
        </Card>
      )}
      {valide && state === "loading" && <Squelette />}
      {valide && state === "ready" && data && <Contenu data={data} />}
    </div>
  );
}

function Squelette() {
  return (
    <div className="space-y-5" aria-busy="true">
      <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-[120px] rounded-card" />
        ))}
      </div>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)]">
        <Skeleton className="h-[340px] rounded-card" />
        <Skeleton className="h-[340px] rounded-card" />
      </div>
      <LoadingState rows={4} />
    </div>
  );
}

function Contenu({ data }: { data: Dashboard }) {
  return (
    <div className="space-y-5">
      <KpiTiles data={data} />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)]">
        <EvolutionCard data={data} />
        <FraisRepartition data={data} />
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]">
        <ComptesCard data={data} />
        <DernieresCard data={data} />
      </div>

      <SyntheseCards data={data} />
    </div>
  );
}
