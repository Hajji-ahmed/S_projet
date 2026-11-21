"use client";

import { Calculator, Coins, Download, FileSpreadsheet, FileUp } from "lucide-react";
import { useCallback, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { useCompany } from "@/components/company/CompanyProvider";
import { ExportSageModal } from "@/components/rapprochement/ExportSageModal";
import {
  FiltreRapprochement,
  useFiltreRapprochement,
} from "@/components/rapprochement/FiltreRapprochement";
import { FraisCard } from "@/components/rapprochement/FraisCard";
import { MatchPanel } from "@/components/rapprochement/MatchPanel";
import { TransactionsPane } from "@/components/rapprochement/TransactionsPane";
import { Button } from "@/components/ui/Button";
import { KpiCard } from "@/components/ui/KpiCard";
import { Modal } from "@/components/ui/Modal";
import { PageHeader } from "@/components/ui/PageHeader";
import { useToast } from "@/components/ui/Toast";
import { signalerAComptabiliser } from "@/lib/aComptabiliser";
import { ApiError } from "@/lib/api";
import { formatAmount, formatNombre } from "@/lib/format";
import { PERMISSIONS, hasAnyPermission } from "@/lib/permissions";
import { A_COMPTABILISER, type ReconciliationFilter } from "@/lib/reconciliation";
import { saveFile } from "@/lib/statements";
import { exporterJustificatif } from "@/services/frais";
import { runReconciliation } from "@/services/reconciliation";
import type { Operation, OperationsPage } from "@/types/reconciliation";

/**
 * Page « À comptabiliser » (21/11/2026, onglet de /rapprochement depuis le 11/11/2026) : les frais
 * bancaires que SIMTIS comptabilise, leurs exports pour la banque et pour Sage, et les opérations
 * de frais encore non rapprochées de la société active.
 */
export function AComptabiliserView() {
  const { company } = useCompany();
  // Changer de société repart d'une page vierge : rien ne se mélange entre deux sociétés
  return company ? <AComptabiliser key={company.id} companyId={company.id} /> : null;
}

function plural(n: number, word: string): string {
  return `${n} ${word}${n > 1 ? "s" : ""}`;
}

function AComptabiliser({ companyId }: { companyId: number }) {
  const { user } = useAuth();
  const { toast } = useToast();
  const canValidate =
    !!user && hasAnyPermission(user.permissions, [PERMISSIONS.RECONCILIATION_VALIDATE]);
  const canPrepare = !!user && hasAnyPermission(user.permissions, [PERMISSIONS.ACCOUNTING_PREPARE]);

  const { filter, changeFilter, periodeLue, periodError, accounts } =
    useFiltreRapprochement(companyId);
  const [reloadKey, setReloadKey] = useState(0);
  const [operation, setOperation] = useState<Operation | null>(null);
  const [resume, setResume] = useState<{ nombre: number; total: string } | null>(null);
  // Écritures de frais pas encore exportées : un seul export pour Sage (13/10/2026)
  const [totalAExporter, setTotalAExporter] = useState<number | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportSage, setExportSage] = useState(false);

  function reload(message: string) {
    toast(message);
    setReloadKey((key) => key + 1);
    signalerAComptabiliser();
  }

  function changerFiltre(next: Partial<ReconciliationFilter>) {
    setOperation(null);
    changeFilter(next);
  }

  const handleOperations = useCallback((page: OperationsPage) => {
    setResume({ nombre: page.a_comptabiliser ?? 0, total: page.total_a_comptabiliser ?? "0" });
    setOperation((current) =>
      current ? (page.operations.find((row) => row.id === current.id) ?? current) : current,
    );
  }, []);

  /** Frais de plus de 200 DH à envoyer à la banque (19/10/2026) : ne marque rien. */
  async function exporterPourBanque() {
    setExporting(true);
    try {
      const blob = await exporterJustificatif(companyId, filter);
      saveFile(blob, `frais-a-justifier-${filter.from}-${filter.to}.xlsx`);
      toast("Frais à justifier exportés pour la banque.");
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "L'export a échoué.", "error");
    } finally {
      setExporting(false);
    }
  }

  /** Frais inclus dans une écriture Sage : le moteur de rapprochement les propose. */
  async function run() {
    try {
      const result = await runReconciliation(companyId, filter);
      reload(
        `Rapprochement lancé : ${plural(result.nb_propositions, "proposition")}, dont ${plural(result.nb_fortes, "forte")}.`,
      );
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Le rapprochement a échoué.", "error");
    }
  }

  const filterKey = `${filter.bankAccountId ?? "tous"}|${filter.from}|${filter.to}`;
  const pret = periodeLue && !periodError;

  return (
    <>
      <PageHeader
        title={A_COMPTABILISER}
        description="Frais bancaires à comptabiliser par SIMTIS et à exporter pour Sage"
        actions={
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              icon={FileSpreadsheet}
              disabled={exporting || !pret}
              onClick={exporterPourBanque}
              title="Frais de plus de 200 DH (hors droits de timbre et commissions avec TVA séparée) à justifier"
            >
              Exporter pour la banque
            </Button>
            {canPrepare && (
              <Button
                icon={Download}
                disabled={exporting || !pret}
                onClick={() => setExportSage(true)}
              >
                Exporter pour Sage
              </Button>
            )}
          </div>
        }
      />

      <FiltreRapprochement
        idPrefix="a-comptabiliser"
        filter={filter}
        accounts={accounts}
        periodError={periodError}
        onChange={changerFiltre}
      />

      {pret && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <KpiCard
            title="Frais à comptabiliser"
            value={resume ? formatNombre(resume.nombre) : "-"}
            icon={Calculator}
          />
          <KpiCard
            title="Montant des frais"
            value={resume ? formatAmount(resume.total, "DH", { dashForZero: true }) : "-"}
            icon={Coins}
          />
          <KpiCard
            title="Écritures à exporter pour Sage"
            value={totalAExporter === null ? "-" : formatNombre(totalAExporter)}
            icon={FileUp}
          />
        </div>
      )}

      {exportSage && (
        <ExportSageModal
          companyId={companyId}
          onClose={() => setExportSage(false)}
          onExported={(message) => {
            setExportSage(false);
            reload(message);
          }}
        />
      )}

      {pret && (
        <div className="space-y-5">
          <FraisCard
            companyId={companyId}
            filter={filter}
            reloadKey={reloadKey}
            canPrepare={canPrepare}
            onChanged={reload}
            onAExporter={setTotalAExporter}
            onLancer={canValidate ? run : undefined}
          />
          {/* Pas de panier sur cette page : un clic sur une ligne ouvre son détail ; le statut
              reste « À comptabiliser » (les autres sont sur /rapprochement) */}
          <TransactionsPane
            key={`frais-${filterKey}`}
            pleinEcran={false}
            companyId={companyId}
            filter={filter}
            reloadKey={reloadKey}
            selectedId={operation?.id ?? null}
            coches={{ ids: [], onToggle: setOperation }}
            onSelect={setOperation}
            onLoaded={handleOperations}
            statut={A_COMPTABILISER}
            onStatutChange={() => undefined}
          />
        </div>
      )}

      <Modal open={!!operation} onClose={() => setOperation(null)} title="Détail du rapprochement">
        {operation && (
          <MatchPanel
            key={operation.id}
            operation={operation}
            entry={null}
            canValidate={canValidate}
            reloadKey={reloadKey}
            onChanged={reload}
          />
        )}
      </Modal>
    </>
  );
}
