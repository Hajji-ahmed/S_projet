"use client";

import {
  ChevronDown,
  CircleCheck,
  FileSpreadsheet,
  History,
  Plus,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { BankLabel, logosByCode } from "@/components/banks/BankLabel";
import { useCompany } from "@/components/company/CompanyProvider";
import { AccountingImportWizard } from "@/components/ecritures/AccountingImportWizard";
import { EntriesCard } from "@/components/ecritures/EntriesCard";
import { DeleteImportModal } from "@/components/imports/DeleteImportModal";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { PageHeader } from "@/components/ui/PageHeader";
import { useToast } from "@/components/ui/Toast";
import { formatDate } from "@/lib/balances";
import { formatAmount } from "@/lib/format";
import { PERMISSIONS, hasAnyPermission } from "@/lib/permissions";
import { IMPORTS_AFFICHES, formatDateTime, showFirst } from "@/lib/statements";
import { listAccountingImports, supprimerImportComptable } from "@/services/accounting";
import { listAccounts } from "@/services/accounts";
import { listBanks } from "@/services/banks";
import type { Account } from "@/types/account";
import type { ConfirmationComptable, ImportComptable } from "@/types/accounting";

/**
 * Page Écritures comptables (P10) : import d'un export Sage / SI de la société active, écritures de
 * trésorerie importées (lecture seule, 50 par page) et journal des imports.
 */
export function EcrituresView() {
  const { company } = useCompany();
  // Changer de société repart d'une page vierge : rien ne se mélange entre deux sociétés
  return company ? <Ecritures key={company.id} companyId={company.id} /> : null;
}

function Ecritures({ companyId }: { companyId: number }) {
  const { user } = useAuth();
  const { toast } = useToast();
  const canImport = !!user && hasAnyPermission(user.permissions, [PERMISSIONS.ACCOUNTING_IMPORT]);

  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<ConfirmationComptable | null>(null);
  const [logos, setLogos] = useState<Map<string, string | null>>(new Map());
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [imports, setImports] = useState<ImportComptable[]>([]);
  const [importsState, setImportsState] = useState<"loading" | "error" | "ready">("loading");
  const [reloadKey, setReloadKey] = useState(0);
  const [shownImports, setShownImports] = useState(IMPORTS_AFFICHES);
  // Suppression d'un import (23/10/2026)
  const [aSupprimer, setASupprimer] = useState<ImportComptable | null>(null);

  // Logos et comptes : sans eux, les codes s'affichent seuls et le filtre par compte disparaît
  useEffect(() => {
    let cancelled = false;
    listBanks().then(
      (banks) => {
        if (!cancelled) setLogos(logosByCode(banks));
      },
      () => undefined,
    );
    listAccounts(companyId, { actif: true }).then(
      (list) => {
        if (!cancelled) setAccounts(list.filter((account) => account.journal_sage));
      },
      () => undefined,
    );
    return () => {
      cancelled = true;
    };
  }, [companyId]);

  useEffect(() => {
    let cancelled = false;
    listAccountingImports(companyId).then(
      (list) => {
        if (cancelled) return;
        setImports(list);
        setShownImports(IMPORTS_AFFICHES);
        setImportsState("ready");
      },
      () => {
        if (!cancelled) setImportsState("error");
      },
    );
    return () => {
      cancelled = true;
    };
  }, [companyId, reloadKey]);

  function reload() {
    setImportsState("loading");
    setReloadKey((key) => key + 1);
  }

  function handleDone(confirmation: ConfirmationComptable) {
    setImporting(false);
    setResult(confirmation);
    const n = confirmation.nb_importees;
    toast(`Export importé : ${n} écriture${n > 1 ? "s" : ""} ajoutée${n > 1 ? "s" : ""}.`);
    reload();
  }

  const journal = showFirst(imports, shownImports, IMPORTS_AFFICHES);
  const columns: Column<ImportComptable>[] = [
    {
      key: "importe_le",
      header: "Importé le",
      render: (row) => (
        <span className="whitespace-nowrap">
          <span className="block">{formatDateTime(row.importe_le)}</span>
          <span className="block text-xs text-simtis-muted">{row.importe_par ?? "-"}</span>
        </span>
      ),
    },
    { key: "fichier_nom", header: "Fichier" },
    {
      key: "periode",
      header: "Période",
      render: (row) => (
        <span className="whitespace-nowrap">
          {row.periode_debut
            ? `${formatDate(row.periode_debut)} au ${formatDate(row.periode_fin)}`
            : "-"}
        </span>
      ),
    },
    { key: "nb_ecritures", header: "Écritures ajoutées", align: "right" },
    {
      key: "totaux",
      header: "Total débit / crédit",
      align: "right",
      render: (row) =>
        `${formatAmount(row.total_debit, "DH")} / ${formatAmount(row.total_credit, "DH")}`,
    },
  ];

  const actionsColumn: Column<ImportComptable>[] = canImport
    ? [
        {
          key: "supprimer",
          header: "",
          align: "right",
          render: (row) =>
            row.statut === "Annulé" ? (
              <span className="rounded-full bg-simtis-neutral-bg px-2 py-0.5 text-xs font-medium text-simtis-neutral-fg">
                Annulé
              </span>
            ) : (
              <button
                type="button"
                onClick={() => setASupprimer(row)}
                disabled={false}
                title={"Supprimer cet import"}
                aria-label={`Supprimer l'import ${row.fichier_nom}`}
                className="rounded-[10px] p-2 text-simtis-danger-fg transition-colors duration-150 hover:bg-simtis-danger-bg disabled:pointer-events-none disabled:opacity-40"
              >
                <Trash2 className="h-4 w-4" aria-hidden />
              </button>
            ),
        },
      ]
    : [];

  const importButton = canImport && !importing && (
    <Button icon={Plus} onClick={() => setImporting(true)}>
      Importer un export Sage
    </Button>
  );

  return (
    <>
      <PageHeader
        title="Écritures comptables"
        description="Écritures de trésorerie importées de Sage / SI"
        actions={importButton}
      />

      {importing && (
        <Card title="Importer un export Sage" icon={Upload}>
          <AccountingImportWizard
            companyId={companyId}
            logos={logos}
            onDone={handleDone}
            onCancel={() => setImporting(false)}
          />
        </Card>
      )}

      {result && (
        <section
          aria-label="Résultat de l'import"
          className="rounded-card border border-l-4 border-simtis-border border-l-simtis-success bg-simtis-card p-5 shadow-simtis"
        >
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <CircleCheck className="mt-0.5 h-5 w-5 shrink-0 text-simtis-success" aria-hidden />
              <div className="space-y-1 text-sm">
                <p className="font-semibold text-simtis-text">
                  {result.fichier_nom} : {result.nb_importees} écriture
                  {result.nb_importees > 1 ? "s" : ""} ajoutée{result.nb_importees > 1 ? "s" : ""}
                  {result.periode_debut &&
                    `, du ${formatDate(result.periode_debut)} au ${formatDate(result.periode_fin)}`}
                  .
                </p>
                <ul className="flex flex-wrap gap-x-5 gap-y-1">
                  {result.par_compte.map((item) => (
                    <li key={item.bank_account_id} className="flex items-center gap-2">
                      <BankLabel code={item.bank_code} logo={logos.get(item.bank_code)}>
                        {item.bank_code} · {item.journal}
                      </BankLabel>
                      <span className="text-simtis-muted tabular-nums">{item.nb}</span>
                    </li>
                  ))}
                </ul>
                {(result.nb_erreurs_ecartees > 0 || result.nb_doublons_ecartes > 0) && (
                  <p className="text-simtis-muted">
                    Écartées : {result.nb_erreurs_ecartees} en erreur, {result.nb_doublons_ecartes}{" "}
                    en double.
                  </p>
                )}
                {result.modele_enregistre && (
                  <p className="text-simtis-muted">
                    Les colonnes sont mémorisées pour les prochains exports de cette société.
                  </p>
                )}
              </div>
            </div>
            <button
              type="button"
              onClick={() => setResult(null)}
              aria-label="Fermer le résultat de l'import"
              className="rounded-lg p-1 text-simtis-muted transition-colors hover:bg-simtis-light hover:text-simtis-primary"
            >
              <X className="h-5 w-5" aria-hidden />
            </button>
          </div>
        </section>
      )}

      <EntriesCard
        companyId={companyId}
        accounts={accounts}
        logos={logos}
        reloadKey={reloadKey}
        canEdit={canImport}
      />

      {aSupprimer && (
        <DeleteImportModal
          fichier={aSupprimer.fichier_nom}
          resume={`${aSupprimer.periode_debut ? `${formatDate(aSupprimer.periode_debut)} au ${formatDate(aSupprimer.periode_fin)}` : "-"} · ${aSupprimer.nb_ecritures} écriture${aSupprimer.nb_ecritures > 1 ? "s" : ""}`}
          onClose={() => setASupprimer(null)}
          onConfirm={async (motif) => {
            const { nb_lignes } = await supprimerImportComptable(aSupprimer.id, motif);
            setASupprimer(null);
            toast(
              `Import supprimé : ${nb_lignes} écriture${nb_lignes > 1 ? "s" : ""} retirée${nb_lignes > 1 ? "s" : ""}.`,
            );
            reload();
          }}
        />
      )}

      <Card title="Journal des imports" icon={History}>
        {importsState === "loading" && <LoadingState rows={3} />}
        {importsState === "error" && (
          <ErrorState message="Impossible de charger le journal des imports." onRetry={reload} />
        )}
        {importsState === "ready" &&
          (imports.length === 0 ? (
            <EmptyState
              icon={FileSpreadsheet}
              message="Aucun export Sage importé."
              action={importButton || undefined}
            />
          ) : (
            <>
              <DataTable
                columns={[...columns, ...actionsColumn]}
                rows={journal.rows}
                getRowKey={(row) => String(row.id)}
                isRowMuted={(row) => row.statut === "Annulé"}
              />
              {journal.hidden > 0 && (
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm">
                  <p className="text-simtis-muted">
                    {journal.rows.length} derniers imports sur {imports.length}
                  </p>
                  <Button
                    variant="ghost"
                    icon={ChevronDown}
                    onClick={() => setShownImports((count) => count + IMPORTS_AFFICHES)}
                    className="h-auto min-h-10 px-0 whitespace-normal"
                  >
                    Afficher {journal.next} de plus
                  </Button>
                </div>
              )}
            </>
          ))}
      </Card>
    </>
  );
}
