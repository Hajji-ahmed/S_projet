"use client";

import { FileDown } from "lucide-react";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { useCompany } from "@/components/company/CompanyProvider";
import { BanquesTable } from "@/components/position/BanquesTable";
import { DevisesTable } from "@/components/position/DevisesTable";
import { PrevisionsTable } from "@/components/position/PrevisionsTable";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { DateInput } from "@/components/ui/Field";
import { LoadingState } from "@/components/ui/LoadingState";
import { PageHeader } from "@/components/ui/PageHeader";
import { ApiError } from "@/lib/api";
import { businessToday } from "@/lib/balances";
import { PERMISSIONS, hasAnyPermission } from "@/lib/permissions";
import { saveFile } from "@/lib/statements";
import { listBanks } from "@/services/banks";
import { exportPositionPdf } from "@/services/rapports";
import type { Bank } from "@/types/bank";

type LoadState = "loading" | "error" | "ready";

/**
 * Page Position bancaire : tableau Banques calculé (P8.1), puis tableaux Devises et Prévisions de
 * la société active, saisis à la main pour une date (en attendant P9 et P14).
 */
export function PositionView() {
  const { user } = useAuth();
  const companyId = useCompany().company?.id;
  const permissions = user?.permissions ?? [];
  const canEnterDevises = hasAnyPermission(permissions, [PERMISSIONS.BANKS_MANAGE]);
  const canEnterPrevisions = hasAnyPermission(permissions, [PERMISSIONS.FORECASTS_MANAGE]);

  const [jour, setJour] = useState(() => businessToday());
  const [banks, setBanks] = useState<Bank[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [reloadKey, setReloadKey] = useState(0);
  const [exportEnCours, setExportEnCours] = useState(false);
  const [erreurExport, setErreurExport] = useState<string | null>(null);

  // Tableau Banques à la date choisie, en PDF (27/10/2026)
  async function exporterPdf() {
    if (!companyId) return;
    setExportEnCours(true);
    setErreurExport(null);
    try {
      // apiDownload rend le fichier : c'est à l'écran de le faire enregistrer
      saveFile(
        await exportPositionPdf(companyId, jour),
        `position-${jour.replaceAll("-", "")}.pdf`,
      );
    } catch (error) {
      setErreurExport(error instanceof ApiError ? error.message : "Export PDF impossible.");
    } finally {
      setExportEnCours(false);
    }
  }

  // Colonnes des tableaux : les banques actives, dans l'ordre d'affichage
  useEffect(() => {
    let cancelled = false;
    listBanks().then(
      (list) => {
        if (cancelled) return;
        setBanks(list.filter((bank) => bank.actif));
        setLoadState("ready");
      },
      () => {
        if (!cancelled) setLoadState("error");
      },
    );
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  return (
    <>
      <PageHeader
        title="Position bancaire"
        description="Tableau Banques calculé ; Devises et Prévisions saisis à la main"
        actions={
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-sm font-medium text-simtis-text">
              Date
              <DateInput
                id="position-date"
                value={jour}
                // Un champ vidé garde la date précédente : une grille appartient toujours à une date
                onChange={(event) => event.target.value && setJour(event.target.value)}
                className="w-[170px]"
              />
            </label>
            <Button
              variant="secondary"
              icon={FileDown}
              onClick={exporterPdf}
              disabled={!companyId || exportEnCours}
            >
              {exportEnCours ? "Export..." : "Exporter en PDF"}
            </Button>
          </div>
        }
      />
      {erreurExport && (
        <p role="alert" className="mb-3 text-sm text-simtis-danger-fg">
          {erreurExport}
        </p>
      )}

      {loadState === "loading" && (
        <Card>
          <LoadingState rows={4} />
        </Card>
      )}
      {loadState === "error" && (
        <Card>
          <ErrorState
            message="Impossible de charger les banques."
            onRetry={() => {
              setLoadState("loading");
              setReloadKey((key) => key + 1);
            }}
          />
        </Card>
      )}
      {loadState === "ready" && companyId !== undefined && (
        <>
          <BanquesTable key={`banques-${companyId}-${jour}`} companyId={companyId} jour={jour} />
          <DevisesTable
            key={`devises-${companyId}-${jour}`}
            companyId={companyId}
            jour={jour}
            banks={banks}
            canEdit={canEnterDevises}
          />
          <PrevisionsTable
            key={`previsions-${companyId}-${jour}`}
            companyId={companyId}
            jour={jour}
            banks={banks}
            canEdit={canEnterPrevisions}
          />
        </>
      )}
    </>
  );
}
