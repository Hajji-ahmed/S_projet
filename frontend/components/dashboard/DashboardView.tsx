"use client";

import { BarChart3, ClipboardList } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { BankPicker } from "@/components/banks/BankPicker";
import { ComptesCard } from "@/components/dashboard/ComptesCard";
import { EvolutionCard } from "@/components/dashboard/EvolutionCard";
import { FraisParBanque } from "@/components/dashboard/FraisParBanque";
import { FraisRepartition } from "@/components/dashboard/FraisRepartition";
import { KpiTiles } from "@/components/dashboard/KpiTiles";
import { PeriodePicker } from "@/components/dashboard/PeriodePicker";
import { ActiviteCard, BanquesCard, TachesCard } from "@/components/dashboard/SuiviCards";
import { Alertes, EcrituresCard, RapprochementCard } from "@/components/dashboard/SyntheseCards";
import { useCompany } from "@/components/company/CompanyProvider";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState, Skeleton } from "@/components/ui/LoadingState";
import { PageHeader } from "@/components/ui/PageHeader";
import { businessToday } from "@/lib/balances";
import { cn } from "@/lib/cn";
import { moisEnCours } from "@/lib/dashboard";
import { PERMISSIONS, hasAnyPermission } from "@/lib/permissions";
import { getDashboard } from "@/services/dashboard";
import type { Dashboard } from "@/types/dashboard";

type Onglet = "suivi" | "indicateurs";

const ONGLETS = [
  ["suivi", "Suivi", ClipboardList],
  ["indicateurs", "Indicateurs", BarChart3],
] as const;

/**
 * Dashboard (P15) : la vue d'ensemble de la société active sur une période (le mois en cours par
 * défaut). Deux onglets (19/10/2026) : « Suivi » (alertes, tâches, avancement, activité) et
 * « Indicateurs » (KPI, évolution, frais, comptes), avec un filtre par banque commun. L'onglet,
 * la banque et la période restent dans l'adresse. Tous les chiffres viennent de l'API
 * (`GET /api/dashboard`) ; les totaux ne portent que sur les comptes courants MAD.
 */
export function DashboardView() {
  const { company } = useCompany();
  return company ? <DashboardSociete key={company.id} companyId={company.id} /> : null;
}

function DashboardSociete({ companyId }: { companyId: number }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const { user } = useAuth();
  const voitHistorique = !!user && hasAnyPermission(user.permissions, [PERMISSIONS.AUDIT_VIEW]);
  const onglet: Onglet = params.get("onglet") === "indicateurs" ? "indicateurs" : "suivi";
  const banque = Number(params.get("banque")) || undefined;
  const [periode, setPeriode] = useState(() => {
    const defaut = moisEnCours(businessToday());
    return { from: params.get("from") || defaut.from, to: params.get("to") || defaut.to };
  });
  const [data, setData] = useState<Dashboard | null>(null);
  const [state, setState] = useState<"loading" | "error" | "ready">("loading");
  const [retry, setRetry] = useState(0);
  const valide = periode.from !== "" && periode.to !== "" && periode.from <= periode.to;

  useEffect(() => {
    if (!valide) return;
    let cancelled = false;
    getDashboard(companyId, periode.from, periode.to, banque).then(
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
  }, [companyId, periode, valide, retry, banque]);

  /** Met à jour l'adresse (onglet, banque, période) sans recharger la page. */
  function adresse(changes: Record<string, string | undefined>) {
    const suivants = new URLSearchParams(params.toString());
    for (const [cle, valeur] of Object.entries(changes)) {
      if (valeur) suivants.set(cle, valeur);
      else suivants.delete(cle);
    }
    const texte = suivants.toString();
    router.replace(texte ? `${pathname}?${texte}` : pathname, { scroll: false });
  }

  function changer(cle: "from" | "to", valeur: string) {
    setState("loading");
    setPeriode((courante) => ({ ...courante, [cle]: valeur }));
    adresse({ [cle]: valeur });
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description="Vue d'ensemble de la position bancaire, du rapprochement et des prévisions"
        actions={
          <div className="flex flex-wrap items-center gap-3">
            <BankPicker
              id="dashboard-banque"
              banques={data?.banques_societe ?? []}
              value={banque}
              onChange={(id) => {
                setState("loading");
                adresse({ banque: id === undefined ? undefined : String(id) });
              }}
            />
            <PeriodePicker periode={periode} onChange={changer} />
          </div>
        }
      />

      <div
        className="flex gap-2 border-b border-simtis-border"
        role="tablist"
        aria-label="Vue du dashboard"
      >
        {ONGLETS.map(([value, label, Icon]) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={onglet === value}
            onClick={() => adresse({ onglet: value === "suivi" ? undefined : value })}
            className={cn(
              "-mb-px flex items-center gap-2 border-b-2 px-3 py-2 text-sm font-medium transition-colors duration-200",
              onglet === value
                ? "border-simtis-primary text-simtis-primary-dark"
                : "border-transparent text-simtis-muted hover:text-simtis-primary",
            )}
          >
            <Icon className="h-4 w-4" aria-hidden />
            {label}
          </button>
        ))}
      </div>

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
      {valide && state === "ready" && data && onglet === "suivi" && (
        <Suivi data={data} voitHistorique={voitHistorique} />
      )}
      {valide && state === "ready" && data && onglet === "indicateurs" && (
        <Indicateurs data={data} />
      )}
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

/** Onglet « Suivi » : le travail du jour. */
function Suivi({ data, voitHistorique }: { data: Dashboard; voitHistorique: boolean }) {
  return (
    <div className="space-y-5">
      <div className="grid gap-5 xl:grid-cols-2">
        <Alertes alertes={data.alertes} />
        <TachesCard data={data} />
      </div>
      <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
        <RapprochementCard data={data} />
        <EcrituresCard data={data} />
        {/* Sur 2 colonnes, la 3e carte prend toute la largeur au lieu de laisser un vide */}
        <BanquesCard data={data} className="sm:col-span-2 xl:col-span-1" />
      </div>
      {voitHistorique && <ActiviteCard />}
    </div>
  );
}

/** Onglet « Indicateurs » : les KPI et les graphiques. */
function Indicateurs({ data }: { data: Dashboard }) {
  const toutes = data.bank_id === null;
  return (
    <div className="space-y-5">
      <KpiTiles data={data} />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)]">
        <EvolutionCard data={data} />
        <FraisRepartition data={data} />
      </div>

      <div className={cn("grid gap-5", toutes && "xl:grid-cols-2")}>
        <ComptesCard data={data} />
        {toutes && <FraisParBanque data={data} />}
      </div>
    </div>
  );
}
