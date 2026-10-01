"use client";

import { CircleAlert, Landmark, Pencil, Plus, Power, PowerOff, WalletCards } from "lucide-react";
import Image from "next/image";
import { useEffect, useState } from "react";

import { AccountFormModal } from "@/components/accounts/AccountFormModal";
import { useAuth } from "@/components/auth/AuthProvider";
import { useCompany } from "@/components/company/CompanyProvider";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Field, Select } from "@/components/ui/Field";
import { FilterBar, FilterItem } from "@/components/ui/FilterBar";
import { LoadingState } from "@/components/ui/LoadingState";
import { Modal } from "@/components/ui/Modal";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useToast } from "@/components/ui/Toast";
import { formatPercent } from "@/lib/accounts";
import { ApiError } from "@/lib/api";
import { formatAmount } from "@/lib/format";
import { PERMISSIONS, hasAnyPermission } from "@/lib/permissions";
import { listAccounts, setAccountStatus } from "@/services/accounts";
import { listBanks } from "@/services/banks";
import { listCurrencies } from "@/services/referentiel";
import type { Account, AccountFilters } from "@/types/account";
import type { Bank } from "@/types/bank";
import type { Currency } from "@/types/company";

type FilterValues = { bank_id: string; devise: string; statut: string };
type FormState = null | { mode: "create" } | { mode: "edit"; account: Account };

const NO_FILTER: FilterValues = { bank_id: "", devise: "", statut: "" };
const STATUT_OPTIONS = [
  { value: "actif", label: "Actifs" },
  { value: "inactif", label: "Inactifs" },
];

function toApiFilters(filters: FilterValues): AccountFilters {
  return {
    bank_id: filters.bank_id ? Number(filters.bank_id) : undefined,
    devise: filters.devise || undefined,
    actif: filters.statut ? filters.statut === "actif" : undefined,
  };
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Une erreur est survenue.";
}

function IconAction({
  label,
  icon: Icon,
  onClick,
}: {
  label: string;
  icon: typeof Pencil;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="rounded-lg p-2 text-simtis-muted transition-colors hover:bg-simtis-light hover:text-simtis-primary"
    >
      <Icon className="h-4 w-4" aria-hidden />
    </button>
  );
}

export function AccountsView() {
  const { user } = useAuth();
  const { company } = useCompany();
  const { toast } = useToast();
  const canManage = !!user && hasAnyPermission(user.permissions, [PERMISSIONS.BANKS_MANAGE]);
  const companyId = company?.id;

  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loadState, setLoadState] = useState<"loading" | "error" | "ready">("loading");
  const [reloadKey, setReloadKey] = useState(0);
  const [filters, setFilters] = useState<FilterValues>(NO_FILTER);
  const [banks, setBanks] = useState<Bank[]>([]);
  const [currencies, setCurrencies] = useState<Currency[]>([]);
  const [form, setForm] = useState<FormState>(null);
  const [toDeactivate, setToDeactivate] = useState<Account | null>(null);
  const [deactivateError, setDeactivateError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Listes des filtres et du formulaire (banques, devises)
  useEffect(() => {
    let cancelled = false;
    Promise.all([listBanks(), listCurrencies()]).then(
      ([bankList, currencyList]) => {
        if (cancelled) return;
        setBanks(bankList);
        setCurrencies(currencyList);
      },
      () => undefined, // sans ces listes, les filtres restent vides ; le tableau signale l'erreur
    );
    return () => {
      cancelled = true;
    };
  }, []);

  // Comptes de la société active, selon les filtres
  useEffect(() => {
    if (companyId === undefined) return;
    let cancelled = false;
    listAccounts(companyId, toApiFilters(filters)).then(
      (list) => {
        if (cancelled) return;
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
  }, [companyId, filters, reloadKey]);

  function reload() {
    setLoadState("loading");
    setReloadKey((key) => key + 1);
  }

  function changeFilter(field: keyof FilterValues, value: string) {
    setLoadState("loading");
    setFilters((current) => ({ ...current, [field]: value }));
  }

  function handleSaved(saved: Account, mode: "create" | "edit") {
    setForm(null);
    toast(
      mode === "create"
        ? `Compte ${saved.bank_code} ${saved.devise} créé.`
        : `Compte ${saved.bank_code} ${saved.devise} modifié.`,
    );
    reload();
  }

  async function reactivate(account: Account) {
    try {
      await setAccountStatus(account.id, true);
      toast(`Compte ${account.bank_code} ${account.devise} réactivé.`);
      reload();
    } catch (error) {
      toast(errorMessage(error), "error");
    }
  }

  async function confirmDeactivation() {
    if (!toDeactivate) return;
    setBusy(true);
    setDeactivateError(null);
    try {
      await setAccountStatus(toDeactivate.id, false);
      toast(`Compte ${toDeactivate.bank_code} ${toDeactivate.devise} désactivé.`);
      setToDeactivate(null);
      reload();
    } catch (error) {
      setDeactivateError(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  const columns: Column<Account>[] = [
    {
      key: "bank",
      header: "Banque",
      render: (row) => (
        <span className="flex items-center gap-2.5 font-medium whitespace-nowrap">
          <span className="grid h-7 w-7 shrink-0 place-items-center overflow-hidden rounded-md border border-simtis-border bg-simtis-card">
            {row.bank_logo ? (
              <Image
                src={row.bank_logo}
                alt=""
                width={28}
                height={28}
                className="h-6 w-6 object-contain"
              />
            ) : (
              <Landmark className="h-4 w-4 text-simtis-primary" aria-hidden />
            )}
          </span>
          {row.bank_code}
        </span>
      ),
    },
    { key: "libelle", header: "Libellé" },
    {
      key: "numero",
      header: "Numéro",
      render: (row) => <span className="whitespace-nowrap tabular-nums">{row.numero}</span>,
    },
    { key: "devise", header: "Devise" },
    {
      key: "type_compte",
      header: "Type",
      render: (row) => <span className="whitespace-nowrap">{row.type_compte}</span>,
    },
    {
      key: "credit_autorise",
      header: "LIGNE",
      align: "right",
      render: (row) =>
        formatAmount(row.credit_autorise, row.devise === "MAD" ? "DH" : row.devise, {
          dashForZero: true,
        }),
    },
    {
      key: "taux_interet_pct",
      header: "Taux",
      align: "right",
      render: (row) => formatPercent(row.taux_interet_pct),
    },
    {
      key: "actif",
      header: "Statut",
      render: (row) => <StatusBadge status={row.actif ? "Actif" : "Inactif"} />,
    },
  ];

  if (canManage) {
    columns.push({
      key: "actions",
      header: "Actions",
      align: "right",
      render: (row) => (
        <span className="inline-flex gap-1">
          <IconAction
            label={`Modifier le compte ${row.bank_code} ${row.devise}`}
            icon={Pencil}
            onClick={() => setForm({ mode: "edit", account: row })}
          />
          {row.actif ? (
            <IconAction
              label={`Désactiver le compte ${row.bank_code} ${row.devise}`}
              icon={PowerOff}
              onClick={() => setToDeactivate(row)}
            />
          ) : (
            <IconAction
              label={`Réactiver le compte ${row.bank_code} ${row.devise}`}
              icon={Power}
              onClick={() => reactivate(row)}
            />
          )}
        </span>
      ),
    });
  }

  const filtered = filters.bank_id !== "" || filters.devise !== "" || filters.statut !== "";

  return (
    <>
      <PageHeader
        title="Comptes"
        description={company ? `Comptes bancaires de ${company.nom}` : "Comptes bancaires"}
        actions={
          canManage &&
          company && (
            <Button icon={Plus} onClick={() => setForm({ mode: "create" })}>
              Nouveau compte
            </Button>
          )
        }
      />

      <FilterBar
        active={filtered}
        onReset={() => {
          setLoadState("loading");
          setFilters(NO_FILTER);
        }}
      >
        <FilterItem>
          <Field label="Banque" htmlFor="filtre-banque">
            <Select
              id="filtre-banque"
              value={filters.bank_id}
              onChange={(event) => changeFilter("bank_id", event.target.value)}
              options={banks.map((bank) => ({ value: String(bank.id), label: bank.code }))}
              placeholder="Toutes"
            />
          </Field>
        </FilterItem>
        <FilterItem>
          <Field label="Devise" htmlFor="filtre-devise">
            <Select
              id="filtre-devise"
              value={filters.devise}
              onChange={(event) => changeFilter("devise", event.target.value)}
              options={currencies.map((currency) => ({
                value: currency.code,
                label: currency.code,
              }))}
              placeholder="Toutes"
            />
          </Field>
        </FilterItem>
        <FilterItem>
          <Field label="Statut" htmlFor="filtre-statut">
            <Select
              id="filtre-statut"
              value={filters.statut}
              onChange={(event) => changeFilter("statut", event.target.value)}
              options={STATUT_OPTIONS}
              placeholder="Tous"
            />
          </Field>
        </FilterItem>
      </FilterBar>

      <Card>
        {loadState === "loading" && <LoadingState rows={5} />}
        {loadState === "error" && (
          <ErrorState message="Impossible de charger les comptes." onRetry={reload} />
        )}
        {loadState === "ready" && accounts.length === 0 && (
          <EmptyState
            icon={WalletCards}
            message={
              filtered
                ? "Aucun compte ne correspond à ces filtres."
                : `Aucun compte pour ${company?.nom ?? "cette société"}.`
            }
          />
        )}
        {loadState === "ready" && accounts.length > 0 && (
          <DataTable columns={columns} rows={accounts} getRowKey={(row) => String(row.id)} />
        )}
      </Card>

      {form && company && (
        <AccountFormModal
          account={form.mode === "edit" ? form.account : undefined}
          company={company}
          banks={banks}
          currencies={currencies}
          onClose={() => setForm(null)}
          onSaved={handleSaved}
        />
      )}

      {toDeactivate && (
        <Modal
          open
          title={`Désactiver le compte ${toDeactivate.bank_code} ${toDeactivate.devise} ?`}
          onClose={() => {
            setToDeactivate(null);
            setDeactivateError(null);
          }}
          footer={
            <>
              <Button
                variant="secondary"
                onClick={() => {
                  setToDeactivate(null);
                  setDeactivateError(null);
                }}
                disabled={busy}
              >
                Annuler
              </Button>
              <Button variant="danger" onClick={confirmDeactivation} disabled={busy}>
                {busy ? "Désactivation..." : "Désactiver"}
              </Button>
            </>
          }
        >
          {deactivateError && (
            <div
              role="alert"
              className="mb-4 flex items-start gap-2 rounded-lg bg-simtis-danger-bg px-3 py-2.5 text-simtis-danger-fg"
            >
              <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              <span>{deactivateError}</span>
            </div>
          )}
          <p className="text-simtis-text">
            {toDeactivate.libelle} ({toDeactivate.numero}) ne sera plus proposé dans les nouveaux
            traitements. Son historique est conservé ; un autre compte pourra prendre sa place.
          </p>
        </Modal>
      )}
    </>
  );
}
