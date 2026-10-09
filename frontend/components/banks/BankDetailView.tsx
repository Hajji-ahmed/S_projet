"use client";

import { ArrowLeft, History, Landmark, PenLine, WalletCards } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { BalanceFormModal, type BalanceTarget } from "@/components/balances/BalanceFormModal";
import { useCompany } from "@/components/company/CompanyProvider";
import { Card } from "@/components/ui/Card";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Field, Select } from "@/components/ui/Field";
import { LoadingState } from "@/components/ui/LoadingState";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useToast } from "@/components/ui/Toast";
import { currencySuffix, formatDate } from "@/lib/balances";
import { cn } from "@/lib/cn";
import { formatAmount } from "@/lib/format";
import { PERMISSIONS, hasAnyPermission } from "@/lib/permissions";
import { listAccounts } from "@/services/accounts";
import { listBalances } from "@/services/balances";
import { listBanks } from "@/services/banks";
import type { Account } from "@/types/account";
import type { Balance } from "@/types/balance";
import type { Bank } from "@/types/bank";

type LoadState = "loading" | "error" | "ready";

function amount(value: string | null, devise: string) {
  return (
    <span className={cn(value?.startsWith("-") && "text-simtis-danger")}>
      {formatAmount(value, currencySuffix(devise))}
    </span>
  );
}

/** Détail d'une banque pour la société active : ses comptes avec leurs chiffres, et l'historique. */
export function BankDetailView({ bankId }: { bankId: number }) {
  const { user } = useAuth();
  const { company } = useCompany();
  const { toast } = useToast();
  const canManage = !!user && hasAnyPermission(user.permissions, [PERMISSIONS.BANKS_MANAGE]);
  const companyId = company?.id;

  const [bank, setBank] = useState<Bank | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [reloadKey, setReloadKey] = useState(0);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [history, setHistory] = useState<Balance[]>([]);
  const [historyState, setHistoryState] = useState<LoadState>("loading");
  const [entryFor, setEntryFor] = useState<BalanceTarget | null>(null);

  // Banque et comptes de la société active
  useEffect(() => {
    if (companyId === undefined) return;
    let cancelled = false;
    Promise.all([listBanks(companyId), listAccounts(companyId, { bank_id: bankId })]).then(
      ([banks, list]) => {
        if (cancelled) return;
        setBank(banks.find((item) => item.id === bankId) ?? null);
        setAccounts(list);
        setLoadState("ready");
      },
      () => {
        if (!cancelled) setLoadState("error");
      },
    );
    return () => {
      cancelled = true;
    };
  }, [bankId, companyId, reloadKey]);

  // Compte dont on affiche l'historique : celui choisi, sinon le premier
  const historyAccount = accounts.find((item) => item.id === selectedId) ?? accounts[0] ?? null;
  const historyAccountId = historyAccount?.id;

  useEffect(() => {
    if (historyAccountId === undefined) return;
    let cancelled = false;
    listBalances(historyAccountId).then(
      (rows) => {
        if (cancelled) return;
        setHistory(rows);
        setHistoryState("ready");
      },
      () => {
        if (!cancelled) setHistoryState("error");
      },
    );
    return () => {
      cancelled = true;
    };
  }, [historyAccountId, reloadKey]);

  function reload() {
    setLoadState("loading");
    setHistoryState("loading");
    setReloadKey((key) => key + 1);
  }

  const accountColumns: Column<Account>[] = [
    {
      key: "libelle",
      header: "Compte",
      render: (row) => (
        <span>
          <span className="block font-medium whitespace-nowrap">{row.libelle}</span>
          <span className="block text-xs whitespace-nowrap text-simtis-muted tabular-nums">
            {row.numero}
          </span>
        </span>
      ),
    },
    {
      key: "devise",
      header: "Devise",
      render: (row) => (
        <span className="whitespace-nowrap">
          {row.devise}
          {row.type_compte === "DH convertible" && " · DH convertible"}
        </span>
      ),
    },
    {
      key: "credit_autorise",
      header: "LIGNE",
      align: "right",
      render: (row) => amount(row.credit_autorise, row.devise),
    },
    {
      key: "solde",
      header: "Solde",
      align: "right",
      render: (row) => amount(row.figures?.solde ?? null, row.devise),
    },
    {
      key: "utilise",
      header: "Crédit utilisé",
      align: "right",
      render: (row) => amount(row.figures?.credit_utilise ?? null, row.devise),
    },
    {
      key: "dispo",
      header: "Crédit disponible",
      align: "right",
      render: (row) => amount(row.figures?.credit_disponible ?? null, row.devise),
    },
    {
      key: "position",
      header: "Position disponible",
      align: "right",
      render: (row) => (
        <span className="font-medium text-simtis-primary">
          {amount(row.figures?.position_disponible ?? null, row.devise)}
        </span>
      ),
    },
    {
      key: "maj",
      header: "Mis à jour",
      render: (row) => (
        <span className="whitespace-nowrap">{formatDate(row.figures?.date_maj ?? null)}</span>
      ),
    },
    {
      key: "statut",
      header: "Statut",
      render: (row) => <StatusBadge status={row.actif ? "Actif" : "Inactif"} />,
    },
  ];
  if (canManage) {
    accountColumns.push({
      key: "actions",
      header: "Actions",
      align: "right",
      render: (row) =>
        row.actif ? (
          <button
            type="button"
            onClick={() => setEntryFor({ ...row, soldeReleve: !!row.figures?.solde_releve })}
            aria-label={`Saisir le solde du compte ${row.bank_code} ${row.devise}`}
            title="Saisir le solde"
            className="rounded-lg p-2 text-simtis-muted transition-colors hover:bg-simtis-light hover:text-simtis-primary"
          >
            <PenLine className="h-4 w-4" aria-hidden />
          </button>
        ) : null,
    });
  }

  const devise = historyAccount?.devise ?? "MAD";
  const historyColumns: Column<Balance>[] = [
    {
      key: "date_solde",
      header: "Date",
      render: (row) => <span className="whitespace-nowrap">{formatDate(row.date_solde)}</span>,
    },
    { key: "solde", header: "Solde", align: "right", render: (row) => amount(row.solde, devise) },
    {
      key: "credit_utilise",
      header: "Crédit utilisé",
      align: "right",
      render: (row) => amount(row.credit_utilise, devise),
    },
    { key: "source", header: "Source" },
    { key: "saisi_par", header: "Saisi par", render: (row) => row.saisi_par ?? "-" },
    { key: "commentaire", header: "Commentaire", render: (row) => row.commentaire ?? "" },
  ];

  const back = (
    <Link
      href="/banques"
      className="inline-flex items-center gap-1 text-sm font-medium text-simtis-primary hover:underline"
    >
      <ArrowLeft className="h-4 w-4" aria-hidden /> Banques
    </Link>
  );

  if (loadState === "error") {
    return (
      <>
        {back}
        <Card>
          <ErrorState message="Impossible de charger cette banque." onRetry={reload} />
        </Card>
      </>
    );
  }
  if (loadState === "loading") {
    return (
      <>
        {back}
        <Card>
          <LoadingState rows={4} />
        </Card>
      </>
    );
  }
  if (!bank) {
    return (
      <>
        {back}
        <Card>
          <EmptyState icon={Landmark} message="Banque introuvable." />
        </Card>
      </>
    );
  }

  return (
    <>
      {back}
      <div className="flex items-center gap-4">
        <span className="grid h-14 w-14 shrink-0 place-items-center overflow-hidden rounded-xl border border-simtis-border bg-simtis-card">
          {bank.logo ? (
            <Image
              src={bank.logo}
              alt=""
              width={56}
              height={56}
              className="h-12 w-12 object-contain"
            />
          ) : (
            <Landmark className="h-6 w-6 text-simtis-primary" aria-hidden />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <PageHeader
            title={bank.nom}
            description={`Code ${bank.code} · comptes de ${company?.nom ?? "la société active"}`}
          />
        </div>
      </div>

      <Card title="Comptes" icon={WalletCards}>
        {accounts.length === 0 ? (
          <EmptyState
            icon={WalletCards}
            message={`Aucun compte chez ${bank.code} pour ${company?.nom ?? "cette société"}.`}
          />
        ) : (
          <DataTable columns={accountColumns} rows={accounts} getRowKey={(row) => String(row.id)} />
        )}
      </Card>

      {historyAccount && (
        <Card title="Historique des soldes" icon={History}>
          <div className="mb-4 max-w-sm">
            <Field label="Compte" htmlFor="historique-compte" hint="30 derniers jours.">
              <Select
                id="historique-compte"
                value={String(historyAccount.id)}
                onChange={(event) => {
                  setHistoryState("loading");
                  setSelectedId(Number(event.target.value));
                }}
                options={accounts.map((item) => ({
                  value: String(item.id),
                  label: `${item.devise} · ${item.libelle} (${item.numero})`,
                }))}
              />
            </Field>
          </div>
          {historyState === "loading" && <LoadingState rows={3} />}
          {historyState === "error" && (
            <ErrorState message="Impossible de charger l'historique." onRetry={reload} />
          )}
          {historyState === "ready" &&
            (history.length === 0 ? (
              <EmptyState icon={History} message="Aucun solde saisi sur les 30 derniers jours." />
            ) : (
              <DataTable
                columns={historyColumns}
                rows={history}
                getRowKey={(row) => String(row.id)}
              />
            ))}
        </Card>
      )}

      {entryFor && (
        <BalanceFormModal
          account={entryFor}
          onClose={() => setEntryFor(null)}
          onSaved={(saved) => {
            setEntryFor(null);
            toast(`Solde du ${formatDate(saved.date_solde)} enregistré.`);
            reload();
          }}
        />
      )}
    </>
  );
}
