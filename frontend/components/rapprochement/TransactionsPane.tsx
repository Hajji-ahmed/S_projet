"use client";

import { Landmark, Search, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { CodeBadge } from "@/components/rapprochement/CodeBadge";
import { ErrorState } from "@/components/ui/ErrorState";
import { DateInput, Field, Select, TextInput } from "@/components/ui/Field";
import { LoadingState } from "@/components/ui/LoadingState";
import { Pagination } from "@/components/ui/Pagination";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { pageCount } from "@/lib/accounting";
import { formatDate } from "@/lib/balances";
import { formatAmount } from "@/lib/format";
import {
  bornerPeriode,
  unite,
  SENS_VOLET,
  TYPES_OPERATION,
  STATUTS_VOLET,
  type ReconciliationFilter,
} from "@/lib/reconciliation";
import { listTransactions } from "@/services/reconciliation";
import type { Operation, OperationsPage } from "@/types/reconciliation";

type TransactionsPaneProps = {
  companyId: number;
  filter: ReconciliationFilter;
  reloadKey: number;
  selectedId: number | null;
  /** Sélection multiple (P13, 15/10/2026) : une case par ligne, le clic coche ou décoche. */
  multi?: { ids: readonly number[]; onToggle: (row: Operation) => void };
  onSelect: (operation: Operation) => void;
  /** Filtre Statut, piloté aussi par les compteurs de la vue ("" = tous les statuts). */
  statut: string;
  onStatutChange: (statut: string) => void;
  /** Chaque page chargée : la vue met à jour l'opération sélectionnée et le résumé. */
  onLoaded: (page: OperationsPage) => void;
};

/** Volet « Transactions bancaires » : opérations de la période, 50 par page, sélection au clic. */
export function TransactionsPane({
  companyId,
  filter,
  reloadKey,
  selectedId,
  multi,
  onSelect,
  onLoaded,
  statut,
  onStatutChange,
}: TransactionsPaneProps) {
  // Un statut changé depuis les compteurs repart de la première page
  const [shownStatut, setShownStatut] = useState(statut);
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [typeOperation, setTypeOperation] = useState("");
  // Sens et dates propres au volet (19/10/2026)
  const [sens, setSens] = useState("");
  const [du, setDu] = useState("");
  const [au, setAu] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<OperationsPage | null>(null);
  const [state, setState] = useState<"loading" | "error" | "ready">("loading");
  const [retryKey, setRetryKey] = useState(0);
  if (statut !== shownStatut) {
    setShownStatut(statut);
    setPage(1);
    setState("loading");
  }

  const periode = bornerPeriode(filter, du, au);
  const filtresActifs = !!(statut || typeOperation || sens || du || au || q || search);

  useEffect(() => {
    let cancelled = false;
    listTransactions(companyId, {
      ...filter,
      from: periode.from,
      to: periode.to,
      statut: statut || undefined,
      q,
      page,
      typeOperation: typeOperation || undefined,
      sens: sens || undefined,
      sansAVerifier: true,
    }).then(
      (result) => {
        if (cancelled) return;
        setData(result);
        setState("ready");
        onLoaded(result);
      },
      () => {
        if (!cancelled) setState("error");
      },
    );
    return () => {
      cancelled = true;
    };
    // La vue remonte le volet (key) quand la période ou le compte change : on repart page 1
  }, [
    companyId,
    filter,
    periode.from,
    periode.to,
    statut,
    q,
    typeOperation,
    sens,
    page,
    reloadKey,
    retryKey,
    onLoaded,
  ]);

  const pages = data ? pageCount(data.total, data.taille) : 1;
  const caseColumn: Column<Operation>[] = multi
    ? [
        {
          key: "choisie",
          header: "",
          render: (row) => (
            <input
              type="checkbox"
              readOnly
              tabIndex={-1}
              checked={multi.ids.includes(row.id)}
              disabled={row.statut === "Rapprochée"}
              aria-label={`Choisir ${row.libelle}`}
              className="pointer-events-none h-4 w-4 accent-simtis-primary"
            />
          ),
        },
      ]
    : [];
  const columns: Column<Operation>[] = [
    ...caseColumn,
    {
      key: "date_operation",
      header: "Date",
      render: (row) => <span className="whitespace-nowrap">{formatDate(row.date_operation)}</span>,
    },
    {
      key: "libelle",
      header: "Libellé",
      render: (row) => (
        <span className="block min-w-[160px]">
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
      render: (row) => formatAmount(row.debit, unite(row.devise), { dashForZero: true }),
    },
    {
      key: "credit",
      header: "Crédit",
      align: "right",
      render: (row) => formatAmount(row.credit, unite(row.devise), { dashForZero: true }),
    },
    { key: "statut", header: "Statut", render: (row) => <StatusBadge status={row.statut} /> },
    {
      key: "code",
      header: "Code",
      render: (row) => (
        <CodeBadge
          code={row.correspondance?.statut === "Validée" ? row.correspondance.code : null}
        />
      ),
    },
  ];

  return (
    <Card
      title="Transactions bancaires"
      icon={Landmark}
      className="xl:flex xl:h-[calc(100dvh-7rem)] xl:min-h-[480px] xl:flex-col"
    >
      <form
        className="mb-4 flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          setState("loading");
          setPage(1);
          setQ(search.trim());
        }}
      >
        <div className="w-full max-w-[170px]">
          <Field label="Statut" htmlFor="rapprochement-tx-statut">
            <Select
              id="rapprochement-tx-statut"
              value={statut}
              placeholder="Tous les statuts"
              options={STATUTS_VOLET.map((item) => ({ value: item, label: item }))}
              onChange={(event) => onStatutChange(event.target.value)}
            />
          </Field>
        </div>
        <div className="w-full max-w-[150px]">
          <Field label="Type" htmlFor="rapprochement-tx-type">
            <Select
              id="rapprochement-tx-type"
              value={typeOperation}
              placeholder="Tous les types"
              options={TYPES_OPERATION.map((item) => ({ value: item, label: item }))}
              onChange={(event) => {
                setState("loading");
                setPage(1);
                setTypeOperation(event.target.value);
              }}
            />
          </Field>
        </div>
        <div className="w-full max-w-[120px]">
          <Field label="Sens" htmlFor="rapprochement-tx-sens">
            <Select
              id="rapprochement-tx-sens"
              value={sens}
              placeholder="Tous"
              options={SENS_VOLET.map((item) => ({ value: item, label: item }))}
              onChange={(event) => {
                setState("loading");
                setPage(1);
                setSens(event.target.value);
              }}
            />
          </Field>
        </div>
        <div className="w-full max-w-[160px]">
          <Field label="Du" htmlFor="rapprochement-tx-du">
            <DateInput
              id="rapprochement-tx-du"
              value={du}
              min={filter.from}
              max={filter.to}
              onChange={(event) => {
                setState("loading");
                setPage(1);
                setDu(event.target.value);
              }}
            />
          </Field>
        </div>
        <div className="w-full max-w-[160px]">
          <Field label="Au" htmlFor="rapprochement-tx-au">
            <DateInput
              id="rapprochement-tx-au"
              value={au}
              min={filter.from}
              max={filter.to}
              onChange={(event) => {
                setState("loading");
                setPage(1);
                setAu(event.target.value);
              }}
            />
          </Field>
        </div>
        <div className="w-full max-w-[200px]">
          <Field label="Recherche" htmlFor="rapprochement-tx-recherche">
            <TextInput
              id="rapprochement-tx-recherche"
              value={search}
              maxLength={100}
              placeholder="Libellé, référence, code"
              onChange={(event) => setSearch(event.target.value)}
            />
          </Field>
        </div>
        <Button
          type="submit"
          variant="secondary"
          icon={Search}
          aria-label="Rechercher les opérations"
        >
          Rechercher
        </Button>
        <Button
          type="button"
          variant="ghost"
          icon={X}
          disabled={!filtresActifs}
          onClick={() => {
            setState("loading");
            setPage(1);
            onStatutChange("");
            setTypeOperation("");
            setSens("");
            setDu("");
            setAu("");
            setSearch("");
            setQ("");
          }}
        >
          Effacer les filtres
        </Button>
      </form>
      {periode.ajustee && (
        <p className="-mt-2 mb-3 text-xs text-simtis-warning-fg">
          Dates ramenées à la période de l&apos;écran ({formatDate(filter.from)} au{" "}
          {formatDate(filter.to)}).
        </p>
      )}

      {state === "loading" && <LoadingState rows={5} />}
      {state === "error" && (
        <ErrorState
          message="Impossible de charger les opérations."
          onRetry={() => {
            setState("loading");
            setRetryKey((key) => key + 1);
          }}
        />
      )}
      {state === "ready" && data && (
        <>
          <DataTable
            // Nouvelle page : le tableau repart en haut
            key={data.page}
            stickyHeader
            className="xl:min-h-0 xl:flex-1 xl:overflow-y-auto"
            columns={columns}
            rows={data.operations}
            getRowKey={(row) => String(row.id)}
            emptyMessage="Aucune opération sur ces critères."
            onRowClick={multi ? multi.onToggle : onSelect}
            isRowSelected={(row) => (multi ? multi.ids.includes(row.id) : row.id === selectedId)}
            rowLabel={(row) =>
              `Opération du ${formatDate(row.date_operation)}, ${row.libelle}, ${row.statut}`
            }
          />
          <Pagination
            label="Pages des opérations"
            page={data.page}
            pages={pages}
            total={data.total}
            noun="opération"
            onPage={(next) => {
              setState("loading");
              setPage(next);
            }}
          />
        </>
      )}
    </Card>
  );
}
