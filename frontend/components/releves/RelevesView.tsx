"use client";

import { CircleCheck, FileSpreadsheet, History, Plus, Upload, X } from "lucide-react";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { BankLabel, logosByCode } from "@/components/banks/BankLabel";
import { useCompany } from "@/components/company/CompanyProvider";
import { AccountStatementCard } from "@/components/releves/AccountStatementCard";
import { ImportWizard } from "@/components/releves/ImportWizard";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useToast } from "@/components/ui/Toast";
import { currencySuffix, formatDate } from "@/lib/balances";
import { formatAmount } from "@/lib/format";
import { PERMISSIONS, hasAnyPermission } from "@/lib/permissions";
import { accountsWithStatements, formatDateTime } from "@/lib/statements";
import { listBanks } from "@/services/banks";
import { listStatements } from "@/services/statements";
import type { Confirmation, Statement } from "@/types/statement";

type LoadState = "loading" | "error" | "ready";

function period(start: string | null, end: string | null) {
  return start ? `${formatDate(start)} au ${formatDate(end)}` : "-";
}

/**
 * Page Relevés : import d'un relevé Excel, relevé continu de chaque compte (chaque import s'ajoute
 * à la suite), et journal des fichiers importés.
 */
export function RelevesView() {
  const { company } = useCompany();
  // Changer de société repart d'une page vierge : rien ne se mélange entre deux sociétés
  return company ? <Releves key={company.id} companyId={company.id} /> : null;
}

function Releves({ companyId }: { companyId: number }) {
  const { user } = useAuth();
  const { toast } = useToast();
  const canImport = !!user && hasAnyPermission(user.permissions, [PERMISSIONS.STATEMENTS_IMPORT]);

  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<Confirmation | null>(null);
  const [statements, setStatements] = useState<Statement[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [reloadKey, setReloadKey] = useState(0);
  const [chosenAccount, setChosenAccount] = useState<number | null>(null);
  const [logos, setLogos] = useState<Map<string, string | null>>(new Map());

  // Logos des banques : sans cette liste, les codes s'affichent seuls (pas de message d'erreur)
  useEffect(() => {
    let cancelled = false;
    listBanks().then(
      (banks) => {
        if (!cancelled) setLogos(logosByCode(banks));
      },
      () => undefined,
    );
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    listStatements(companyId).then(
      (list) => {
        if (cancelled) return;
        setStatements(list);
        setLoadState("ready");
      },
      () => {
        if (!cancelled) setLoadState("error");
      },
    );
    return () => {
      cancelled = true;
    };
  }, [companyId, reloadKey]);

  function reload() {
    setLoadState("loading");
    setReloadKey((key) => key + 1);
  }

  function handleDone(confirmation: Confirmation) {
    setImporting(false);
    setResult(confirmation);
    // Le relevé du compte importé s'affiche, avec les nouvelles lignes à la suite
    setChosenAccount(confirmation.bank_account_id);
    toast(
      `Relevé importé : ${confirmation.nb_importees} opération${confirmation.nb_importees > 1 ? "s" : ""} ajoutée${confirmation.nb_importees > 1 ? "s" : ""}.`,
    );
    reload();
  }

  const accounts = accountsWithStatements(statements);
  // Compte affiché : celui choisi, sinon celui du dernier import
  const selectedId =
    accounts.find((account) => account.bank_account_id === chosenAccount)?.bank_account_id ??
    statements[0]?.bank_account_id;

  const columns: Column<Statement>[] = [
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
    {
      key: "compte",
      header: "Compte",
      render: (row) => (
        <span className="whitespace-nowrap">
          <BankLabel code={row.bank_code} logo={logos.get(row.bank_code)} className="font-medium">
            {row.bank_code} · {row.devise}
          </BankLabel>
          <span className="block text-xs text-simtis-muted tabular-nums">{row.compte_numero}</span>
        </span>
      ),
    },
    { key: "fichier_nom", header: "Fichier" },
    {
      key: "periode",
      header: "Période",
      render: (row) => (
        <span className="whitespace-nowrap">{period(row.periode_debut, row.periode_fin)}</span>
      ),
    },
    { key: "nb_lignes", header: "Opérations ajoutées", align: "right" },
    {
      key: "solde_cloture",
      header: "Solde de clôture",
      align: "right",
      render: (row) => formatAmount(row.solde_cloture, currencySuffix(row.devise)),
    },
    {
      key: "controle",
      header: "Contrôle du solde",
      render: (row) =>
        row.controle_solde ? (
          <span
            title={`Écart : ${formatAmount(row.controle_solde.ecart, currencySuffix(row.devise))}`}
          >
            <StatusBadge status={row.controle_solde.statut} />
          </span>
        ) : (
          <span className="text-simtis-muted">-</span>
        ),
    },
  ];

  const importButton = canImport && !importing && (
    <Button icon={Plus} onClick={() => setImporting(true)}>
      Importer un relevé
    </Button>
  );

  return (
    <>
      <PageHeader
        title="Relevés bancaires"
        description="Import et consultation des relevés bancaires"
        actions={importButton}
      />

      {importing && (
        <Card title="Importer un relevé" icon={Upload}>
          <ImportWizard
            companyId={companyId}
            onDone={handleDone}
            onCancel={() => setImporting(false)}
          />
        </Card>
      )}

      {result && (
        <ImportResult
          result={result}
          devise={statements.find((row) => row.id === result.statement_id)?.devise}
          onClose={() => setResult(null)}
        />
      )}

      {loadState === "ready" && selectedId !== undefined && (
        <AccountStatementCard
          accounts={accounts}
          selectedId={selectedId}
          onSelect={setChosenAccount}
          logos={logos}
          reloadKey={reloadKey}
        />
      )}

      <Card title="Journal des imports" icon={History}>
        {loadState === "loading" && <LoadingState rows={4} />}
        {loadState === "error" && (
          <ErrorState message="Impossible de charger les relevés." onRetry={reload} />
        )}
        {loadState === "ready" &&
          (statements.length === 0 ? (
            <EmptyState
              icon={FileSpreadsheet}
              message="Aucun relevé bancaire disponible."
              action={importButton || undefined}
            />
          ) : (
            <DataTable columns={columns} rows={statements} getRowKey={(row) => String(row.id)} />
          ))}
      </Card>
    </>
  );
}

/** Résumé du dernier import confirmé : ce qui a été enregistré et le contrôle du solde. */
function ImportResult({
  result,
  devise,
  onClose,
}: {
  result: Confirmation;
  /** Devise du compte, connue dès que le journal est rechargé. */
  devise?: string;
  onClose: () => void;
}) {
  const check = result.controle_solde;
  const money = (value: string | null) =>
    formatAmount(value, devise ? currencySuffix(devise) : undefined);
  const effect = {
    Créé: "enregistré comme solde du jour",
    Corrigé: "a remplacé le solde du jour enregistré",
    Inchangé: "était déjà le solde du jour",
  } as const;

  return (
    <section
      aria-label="Résultat de l'import"
      className="rounded-[14px] border border-l-4 border-simtis-border border-l-simtis-success bg-simtis-card p-5 shadow-simtis"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <CircleCheck className="mt-0.5 h-5 w-5 shrink-0 text-simtis-success" aria-hidden />
          <div className="space-y-1 text-sm">
            <p className="font-semibold text-simtis-text">
              {result.fichier_nom} : {result.nb_importees} opération
              {result.nb_importees > 1 ? "s" : ""} ajoutée{result.nb_importees > 1 ? "s" : ""} au
              relevé du compte, du {formatDate(result.periode_debut)} au{" "}
              {formatDate(result.periode_fin)}.
            </p>
            {(result.nb_erreurs_ecartees > 0 || result.nb_doublons_ecartes > 0) && (
              <p className="text-simtis-muted">
                Écartées : {result.nb_erreurs_ecartees} en erreur, {result.nb_doublons_ecartes} en
                double.
              </p>
            )}
            {result.solde_du_jour && (
              <p className="text-simtis-muted">
                Solde de clôture {money(result.solde_cloture)} au {formatDate(result.periode_fin)} :{" "}
                {effect[result.solde_du_jour]}.
              </p>
            )}
            {check && (
              <p className="flex flex-wrap items-center gap-2">
                <span className="text-simtis-muted">Contrôle du solde :</span>
                <StatusBadge status={check.statut} />
                {check.statut !== "Conforme" && (
                  <span className="text-simtis-muted">
                    enregistré {money(check.solde_enregistre)}, relevé {money(check.solde_releve)},
                    écart {money(check.ecart)}
                  </span>
                )}
              </p>
            )}
            {result.modele_enregistre && (
              <p className="text-simtis-muted">
                Le mapping des colonnes est mémorisé pour les prochains relevés de cette banque.
              </p>
            )}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Fermer le résultat de l'import"
          className="rounded-lg p-1 text-simtis-muted transition-colors hover:bg-simtis-light hover:text-simtis-primary"
        >
          <X className="h-5 w-5" aria-hidden />
        </button>
      </div>
    </section>
  );
}
