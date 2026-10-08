"use client";

import {
  CircleCheck,
  Clock,
  ListChecks,
  Scale,
  Search,
  TriangleAlert,
  Wand2,
  X,
} from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { BankLabel, logosByCode } from "@/components/banks/BankLabel";
import { useCompany } from "@/components/company/CompanyProvider";
import { DiscrepancyPanel } from "@/components/ecarts/DiscrepancyPanel";
import { AccountButton } from "@/components/ecritures/EntriesCard";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { ErrorState } from "@/components/ui/ErrorState";
import { DateInput, Field, Select, TextInput } from "@/components/ui/Field";
import { KpiCard } from "@/components/ui/KpiCard";
import { LoadingState } from "@/components/ui/LoadingState";
import { Pagination } from "@/components/ui/Pagination";
import { Modal } from "@/components/ui/Modal";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useToast } from "@/components/ui/Toast";
import { pageCount } from "@/lib/accounting";
import { ApiError } from "@/lib/api";
import { businessToday, currencySuffix, formatDate } from "@/lib/balances";
import { openTotals, type DiscrepanciesFilter } from "@/lib/discrepancies";
import { formatAmount } from "@/lib/format";
import { PERMISSIONS, hasAnyPermission } from "@/lib/permissions";
import { defaultPeriod } from "@/lib/reconciliation";
import { listAccounts } from "@/services/accounts";
import { listBanks } from "@/services/banks";
import {
  generateDiscrepancies,
  listDiscrepancies,
  listResponsables,
} from "@/services/discrepancies";
import type { Account } from "@/types/account";
import {
  STATUTS_ECART,
  TYPES_ECART,
  type Ecart,
  type EcartsPage,
  type Responsable,
} from "@/types/discrepancy";

/**
 * Page Écarts (P12) : KPI, filtres et liste des écarts de la société active ; un clic ouvre le
 * panneau latéral de détail et de traitement. « Générer les écarts » signale les lignes restées
 * sans pendant et les doublons potentiels d'une période.
 */
export function EcartsView() {
  const { company } = useCompany();
  return company ? <Ecarts key={company.id} companyId={company.id} /> : null;
}

function Ecarts({ companyId }: { companyId: number }) {
  const { user } = useAuth();
  const { toast } = useToast();
  const searchParams = useSearchParams();
  const canManage =
    !!user && hasAnyPermission(user.permissions, [PERMISSIONS.DISCREPANCIES_MANAGE]);

  const [filter, setFilter] = useState<DiscrepanciesFilter>({ page: 1 });
  const [search, setSearch] = useState("");
  const [data, setData] = useState<EcartsPage | null>(null);
  const [state, setState] = useState<"loading" | "error" | "ready">("loading");
  const [reloadKey, setReloadKey] = useState(0);
  const [selectedId, setSelectedId] = useState<number | null>(() => {
    const id = Number(searchParams.get("ecart"));
    return Number.isInteger(id) && id > 0 ? id : null;
  });
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [responsables, setResponsables] = useState<Responsable[]>([]);
  const [logos, setLogos] = useState<Map<string, string | null>>(new Map());
  const [generating, setGenerating] = useState(false);

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
        if (!cancelled) setAccounts(list);
      },
      () => undefined,
    );
    listResponsables(companyId).then(
      (list) => {
        if (!cancelled) setResponsables(list);
      },
      () => undefined,
    );
    return () => {
      cancelled = true;
    };
  }, [companyId]);

  useEffect(() => {
    let cancelled = false;
    listDiscrepancies(companyId, filter).then(
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
  }, [companyId, filter, reloadKey]);

  /** Changer un filtre revient à la première page. */
  function change(next: Partial<DiscrepanciesFilter>) {
    setState("loading");
    setFilter((current) => ({ ...current, ...next, page: next.page ?? 1 }));
  }

  const reload = useCallback(
    (message?: string) => {
      if (message) toast(message);
      setReloadKey((key) => key + 1);
    },
    [toast],
  );

  const pages = data ? pageCount(data.total, data.taille) : 1;
  const filtered =
    !!filter.statut ||
    !!filter.type ||
    filter.responsableId !== undefined ||
    filter.bankAccountId !== undefined ||
    !!filter.from ||
    !!filter.to ||
    !!filter.q;
  const totals = data ? openTotals(data.montants_ouverts) : [];

  const columns: Column<Ecart>[] = [
    {
      key: "date_ecart",
      header: "Date",
      render: (row) => <span className="whitespace-nowrap">{formatDate(row.date_ecart)}</span>,
    },
    {
      key: "type",
      header: "Type",
      render: (row) => <span className="whitespace-nowrap">{row.type}</span>,
    },
    {
      key: "bank_code",
      header: "Banque",
      render: (row) =>
        row.bank_code ? <BankLabel code={row.bank_code} logo={logos.get(row.bank_code)} /> : "-",
    },
    {
      key: "libelle",
      header: "Libellé",
      render: (row) => <span className="block min-w-[180px]">{row.libelle ?? "-"}</span>,
    },
    {
      key: "montant",
      header: "Montant",
      align: "right",
      render: (row) => formatAmount(row.montant, currencySuffix(row.devise ?? "MAD")),
    },
    {
      key: "difference",
      header: "Différence",
      align: "right",
      render: (row) =>
        row.difference === null
          ? "-"
          : formatAmount(row.difference, currencySuffix(row.devise ?? "MAD")),
    },
    { key: "responsable", header: "Responsable", render: (row) => row.responsable ?? "-" },
    {
      key: "statut",
      header: "Statut",
      render: (row) => <StatusBadge status={row.statut} />,
    },
  ];

  return (
    <>
      <PageHeader
        title="Écarts"
        description="Suivi des opérations et écritures non rapprochées, jusqu'à leur clôture"
        actions={
          canManage && (
            <Button icon={Wand2} onClick={() => setGenerating(true)}>
              Générer les écarts
            </Button>
          )
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          title="Écarts à traiter"
          value={data ? String(data.par_statut["À traiter"]) : "-"}
          icon={TriangleAlert}
        />
        <KpiCard
          title="Écarts en cours"
          value={data ? String(data.par_statut["En cours"] + data.par_statut["Traité"]) : "-"}
          icon={Clock}
        />
        <KpiCard
          title="Écarts clôturés"
          value={data ? String(data.par_statut["Clôturé"]) : "-"}
          icon={CircleCheck}
        />
        <KpiCard
          title="Montant total (écarts ouverts)"
          value={
            !data ? "-" : totals.length === 0 ? formatAmount("0", "DH") : formatTotal(totals[0])
          }
          icon={Scale}
        />
      </div>
      {totals.length > 1 && (
        <p className="-mt-2 text-sm text-simtis-muted">
          Autres devises, jamais additionnées au dirham :{" "}
          {totals.slice(1).map(formatTotal).join(" · ")}
        </p>
      )}
      {data && data.par_statut["Traité"] > 0 && (
        <p className="-mt-2 text-sm text-simtis-muted">
          Dont {data.par_statut["Traité"]} traité{data.par_statut["Traité"] > 1 ? "s" : ""} en
          attente de clôture.
        </p>
      )}

      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_400px]">
        <Card title="Écarts" icon={ListChecks}>
          {accounts.length > 0 && (
            <div
              className="mb-4 flex gap-2 overflow-x-auto pb-1"
              role="group"
              aria-label="Compte bancaire"
            >
              <AccountButton
                active={filter.bankAccountId === undefined}
                onClick={() => change({ bankAccountId: undefined })}
              >
                Tous les comptes
              </AccountButton>
              {accounts.map((account) => (
                <AccountButton
                  key={account.id}
                  active={filter.bankAccountId === account.id}
                  onClick={() => change({ bankAccountId: account.id })}
                >
                  <BankLabel code={account.bank_code} logo={account.bank_logo}>
                    {account.bank_code} · {account.devise}
                  </BankLabel>
                </AccountButton>
              ))}
            </div>
          )}

          <form
            className="mb-4 flex flex-wrap items-end gap-3"
            onSubmit={(event) => {
              event.preventDefault();
              change({ q: search.trim() || undefined });
            }}
          >
            <div className="w-full max-w-[170px]">
              <Field label="Statut" htmlFor="ecarts-statut">
                <Select
                  id="ecarts-statut"
                  value={filter.statut ?? ""}
                  placeholder="Tous les statuts"
                  options={STATUTS_ECART.map((item) => ({ value: item, label: item }))}
                  onChange={(event) => change({ statut: event.target.value || undefined })}
                />
              </Field>
            </div>
            <div className="w-full max-w-[200px]">
              <Field label="Type" htmlFor="ecarts-type">
                <Select
                  id="ecarts-type"
                  value={filter.type ?? ""}
                  placeholder="Tous les types"
                  options={TYPES_ECART.map((item) => ({ value: item, label: item }))}
                  onChange={(event) => change({ type: event.target.value || undefined })}
                />
              </Field>
            </div>
            <div className="w-full max-w-[190px]">
              <Field label="Responsable" htmlFor="ecarts-responsable">
                <Select
                  id="ecarts-responsable"
                  value={filter.responsableId === undefined ? "" : String(filter.responsableId)}
                  placeholder="Tous"
                  options={responsables.map((item) => ({
                    value: String(item.id),
                    label: item.nom,
                  }))}
                  onChange={(event) =>
                    change({
                      responsableId: event.target.value ? Number(event.target.value) : undefined,
                    })
                  }
                />
              </Field>
            </div>
            <div className="w-full max-w-[160px]">
              <Field label="Du" htmlFor="ecarts-du">
                <DateInput
                  id="ecarts-du"
                  value={filter.from ?? ""}
                  onChange={(event) => change({ from: event.target.value || undefined })}
                />
              </Field>
            </div>
            <div className="w-full max-w-[160px]">
              <Field label="Au" htmlFor="ecarts-au">
                <DateInput
                  id="ecarts-au"
                  value={filter.to ?? ""}
                  onChange={(event) => change({ to: event.target.value || undefined })}
                />
              </Field>
            </div>
            <div className="w-full max-w-[220px]">
              <Field label="Recherche" htmlFor="ecarts-recherche">
                <TextInput
                  id="ecarts-recherche"
                  value={search}
                  maxLength={100}
                  placeholder="Libellé, pièce, tiers"
                  onChange={(event) => setSearch(event.target.value)}
                />
              </Field>
            </div>
            <Button type="submit" variant="secondary" icon={Search}>
              Rechercher
            </Button>
            {filtered && (
              <Button
                variant="ghost"
                icon={X}
                onClick={() => {
                  setSearch("");
                  setState("loading");
                  setFilter({ page: 1 });
                }}
              >
                Effacer les filtres
              </Button>
            )}
          </form>

          {state === "loading" && <LoadingState rows={6} />}
          {state === "error" && (
            <ErrorState
              message="Impossible de charger les écarts."
              onRetry={() => {
                setState("loading");
                reload();
              }}
            />
          )}
          {state === "ready" && data && (
            <>
              <DataTable
                columns={columns}
                rows={data.ecarts}
                getRowKey={(row) => String(row.id)}
                emptyMessage={
                  filtered ? "Aucun écart sur ces critères." : "Aucun écart pour cette société."
                }
                onRowClick={(row) => setSelectedId(row.id)}
                isRowSelected={(row) => row.id === selectedId}
                rowLabel={(row) =>
                  `Écart ${row.type} du ${formatDate(row.date_ecart)}, ${row.statut}`
                }
              />
              <Pagination
                label="Pages des écarts"
                page={data.page}
                pages={pages}
                total={data.total}
                noun="écart"
                onPage={(page) => change({ page })}
              />
            </>
          )}
        </Card>

        {selectedId !== null && (
          <div className="xl:sticky xl:top-4">
            <DiscrepancyPanel
              key={selectedId}
              ecartId={selectedId}
              canManage={canManage}
              responsables={responsables}
              logos={logos}
              onClose={() => setSelectedId(null)}
              onChanged={reload}
            />
          </div>
        )}
      </div>

      {generating && (
        <GenerateModal
          companyId={companyId}
          accounts={accounts}
          onClose={() => setGenerating(false)}
          onDone={(message) => {
            setGenerating(false);
            setState("loading");
            reload(message);
          }}
        />
      )}
    </>
  );
}

function formatTotal([devise, montant]: [string, string]): string {
  return formatAmount(montant, currencySuffix(devise));
}

function GenerateModal({
  companyId,
  accounts,
  onClose,
  onDone,
}: {
  companyId: number;
  accounts: Account[];
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  const [period, setPeriod] = useState(() => defaultPeriod(businessToday()));
  const [accountId, setAccountId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const invalid = !period.from || !period.to || period.from > period.to;

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const result = await generateDiscrepancies(companyId, {
        ...period,
        bankAccountId: accountId ? Number(accountId) : undefined,
      });
      onDone(
        result.total === 0
          ? "Aucun nouvel écart sur cette période."
          : `${result.total} écart${result.total > 1 ? "s" : ""} créé${result.total > 1 ? "s" : ""} : ` +
              `${result.banque_sans_ecriture} banque sans écriture, ` +
              `${result.ecriture_sans_banque} écriture sans banque, ${result.doublons} doublon` +
              `${result.doublons > 1 ? "s" : ""} potentiel${result.doublons > 1 ? "s" : ""}.`,
      );
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Une erreur est survenue.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Générer les écarts"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Annuler
          </Button>
          <Button icon={Wand2} disabled={busy || invalid} onClick={submit}>
            Générer
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <p className="text-simtis-muted">
          Signale les doublons potentiels de la période, et les opérations ou écritures encore non
          rapprochées datées d&apos;au moins 10 jours (leur pendant peut encore arriver avant). Une
          ligne qui a déjà eu un écart n&apos;est jamais signalée de nouveau.
        </p>
        {error && (
          <p
            role="alert"
            className="rounded-[10px] bg-simtis-danger-bg px-3 py-2 text-simtis-danger-fg"
          >
            {error}
          </p>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Du" htmlFor="generer-du" required>
            <DateInput
              id="generer-du"
              value={period.from}
              onChange={(event) => setPeriod((p) => ({ ...p, from: event.target.value }))}
            />
          </Field>
          <Field label="Au" htmlFor="generer-au" required>
            <DateInput
              id="generer-au"
              value={period.to}
              onChange={(event) => setPeriod((p) => ({ ...p, to: event.target.value }))}
            />
          </Field>
        </div>
        <Field label="Compte bancaire" htmlFor="generer-compte">
          <Select
            id="generer-compte"
            value={accountId}
            placeholder="Tous les comptes"
            options={accounts.map((account) => ({
              value: String(account.id),
              label: `${account.bank_code} · ${account.devise} · ${account.libelle}`,
            }))}
            onChange={(event) => setAccountId(event.target.value)}
          />
        </Field>
      </div>
    </Modal>
  );
}
