"use client";

import { Download, ListOrdered, X } from "lucide-react";
import { useEffect, useState } from "react";

import { BankLabel } from "@/components/banks/BankLabel";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { ErrorState } from "@/components/ui/ErrorState";
import { DateInput, Field } from "@/components/ui/Field";
import { LoadingState } from "@/components/ui/LoadingState";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useToast } from "@/components/ui/Toast";
import { ApiError } from "@/lib/api";
import { currencySuffix, formatDate } from "@/lib/balances";
import { cn } from "@/lib/cn";
import { formatAmount } from "@/lib/format";
import { exportFilename, saveFile, type Period } from "@/lib/statements";
import { exportAccountStatement, getAccountStatement } from "@/services/statements";
import type { AccountStatement, Transaction } from "@/types/statement";
import type { Status } from "@/types/status";

type LoadState = "loading" | "error" | "ready";

/** Compte qui a au moins un relevé importé (tiré du journal des imports). */
export type StatementAccount = {
  bank_account_id: number;
  bank_code: string;
  devise: string;
  compte_numero: string;
};

type AccountStatementCardProps = {
  accounts: StatementAccount[];
  selectedId: number;
  onSelect: (accountId: number) => void;
  logos: Map<string, string | null>;
  /** Incrémenté après un import : le relevé est rechargé avec ses nouvelles lignes. */
  reloadKey: number;
};

/**
 * Relevé continu d'un compte : toutes ses opérations importées, quel que soit le fichier, au
 * format standard. Chaque nouvel import s'ajoute à la suite (décision métier du 02/10/2026).
 */
export function AccountStatementCard({
  accounts,
  selectedId,
  onSelect,
  logos,
  reloadKey,
}: AccountStatementCardProps) {
  const { toast } = useToast();
  const [period, setPeriod] = useState<Period>({});
  const [data, setData] = useState<AccountStatement | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [retryKey, setRetryKey] = useState(0);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getAccountStatement(selectedId, period).then(
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
  }, [selectedId, period, reloadKey, retryKey]);

  function changePeriod(next: Period) {
    setState("loading");
    setPeriod(next);
  }

  async function download() {
    if (!data) return;
    setExporting(true);
    try {
      saveFile(await exportAccountStatement(selectedId, period), exportFilename(data));
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Export impossible.", "error");
    } finally {
      setExporting(false);
    }
  }

  const devise = data?.devise ?? accounts.find((a) => a.bank_account_id === selectedId)?.devise;
  const suffix = currencySuffix(devise ?? "MAD");
  const logo = data ? logos.get(data.bank_code) : undefined;

  // Les 11 colonnes du relevé standard, dans leur ordre, puis le statut de rapprochement
  const columns: Column<Transaction>[] = [
    { key: "societe", header: "Société" },
    { key: "pointage", header: "Pointage", render: (row) => row.pointage ?? "-" },
    {
      key: "banque",
      header: "Banque",
      render: (row) => <BankLabel code={row.banque} logo={logo} />,
    },
    {
      key: "date_operation",
      header: "Date d'opération",
      render: (row) => <span className="whitespace-nowrap">{formatDate(row.date_operation)}</span>,
    },
    {
      key: "date_valeur",
      header: "Date de valeur",
      render: (row) => <span className="whitespace-nowrap">{formatDate(row.date_valeur)}</span>,
    },
    {
      key: "libelle",
      header: "Libellé",
      // Largeur minimale : avec les 12 colonnes du format standard, le libellé serait écrasé
      render: (row) => (
        <span className="block min-w-[260px]">
          <span className="block">{row.libelle}</span>
          {row.reference && (
            <span className="block text-xs text-simtis-muted">Réf. {row.reference}</span>
          )}
        </span>
      ),
    },
    {
      key: "debit",
      header: "Débit",
      align: "right",
      render: (row) => formatAmount(row.debit, suffix, { dashForZero: true }),
    },
    {
      key: "credit",
      header: "Crédit",
      align: "right",
      render: (row) => formatAmount(row.credit, suffix, { dashForZero: true }),
    },
    {
      key: "solde",
      header: "Solde",
      align: "right",
      render: (row) => formatAmount(row.solde, suffix),
    },
    {
      key: "lettrage_escompte",
      header: "Lettrage / Escompte",
      render: (row) => row.lettrage_escompte ?? "-",
    },
    { key: "commentaire", header: "Commentaire", render: (row) => row.commentaire ?? "-" },
    {
      key: "statut",
      header: "Statut",
      render: (row) => <StatusBadge status={row.statut as Status} />,
    },
  ];

  return (
    <Card title="Relevés par compte" icon={ListOrdered}>
      <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label="Compte affiché">
        {accounts.map((account) => {
          const active = account.bank_account_id === selectedId;
          return (
            <button
              key={account.bank_account_id}
              type="button"
              aria-pressed={active}
              onClick={() => {
                if (active) return;
                setState("loading");
                onSelect(account.bank_account_id);
              }}
              className={cn(
                "rounded-[10px] border px-3 py-2 text-sm font-medium transition-colors duration-200",
                active
                  ? "border-simtis-primary bg-simtis-light text-simtis-primary-dark"
                  : "border-simtis-border bg-simtis-card text-simtis-text hover:bg-simtis-light/50",
              )}
            >
              <BankLabel code={account.bank_code} logo={logos.get(account.bank_code)}>
                {account.bank_code} · {account.devise}
                <span className="ml-2 text-xs font-normal text-simtis-muted tabular-nums">
                  {account.compte_numero}
                </span>
              </BankLabel>
            </button>
          );
        })}
      </div>

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="w-full max-w-[180px]">
          <Field label="Du" htmlFor="releve-du">
            <DateInput
              id="releve-du"
              value={period.from ?? ""}
              onChange={(event) => changePeriod({ ...period, from: event.target.value })}
            />
          </Field>
        </div>
        <div className="w-full max-w-[180px]">
          <Field label="Au" htmlFor="releve-au">
            <DateInput
              id="releve-au"
              value={period.to ?? ""}
              onChange={(event) => changePeriod({ ...period, to: event.target.value })}
            />
          </Field>
        </div>
        {(period.from || period.to) && (
          <Button variant="ghost" icon={X} onClick={() => changePeriod({})}>
            Tout l&apos;historique
          </Button>
        )}
        <div className="ml-auto">
          <Button
            variant="secondary"
            icon={Download}
            onClick={download}
            disabled={exporting || state !== "ready" || !data || data.nb_operations === 0}
            aria-label="Exporter le relevé du compte au format standard"
          >
            {exporting ? "Export..." : "Exporter"}
          </Button>
        </div>
      </div>

      {state === "loading" && <LoadingState rows={5} />}
      {state === "error" && (
        <ErrorState
          message="Impossible de charger le relevé de ce compte."
          onRetry={() => {
            setState("loading");
            setRetryKey((key) => key + 1);
          }}
        />
      )}
      {state === "ready" && data && (
        <>
          <dl
            className="mb-4 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2 lg:grid-cols-5"
            aria-label="Résumé du relevé"
          >
            <div>
              <dt className="text-simtis-muted">Période</dt>
              <dd className="font-medium">
                {data.periode_debut
                  ? `${formatDate(data.periode_debut)} au ${formatDate(data.periode_fin)}`
                  : "-"}
              </dd>
            </div>
            <div>
              <dt className="text-simtis-muted">Opérations</dt>
              <dd className="font-medium tabular-nums">{data.nb_operations}</dd>
            </div>
            <div>
              <dt className="text-simtis-muted">Total débit / crédit</dt>
              <dd className="font-medium tabular-nums">
                {formatAmount(data.total_debit, suffix)} / {formatAmount(data.total_credit, suffix)}
              </dd>
            </div>
            <div>
              <dt className="text-simtis-muted">Solde d&apos;ouverture</dt>
              <dd className="font-medium tabular-nums">
                {formatAmount(data.solde_ouverture, suffix)}
              </dd>
            </div>
            <div>
              <dt className="text-simtis-muted">Solde de clôture</dt>
              <dd className="font-medium text-simtis-primary tabular-nums">
                {formatAmount(data.solde_cloture, suffix)}
              </dd>
            </div>
          </dl>
          <DataTable
            columns={columns}
            rows={data.operations}
            getRowKey={(row) => String(row.id)}
            emptyMessage="Aucune opération sur cette période."
          />
        </>
      )}
    </Card>
  );
}
