"use client";

import { Landmark, Search } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { ErrorState } from "@/components/ui/ErrorState";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { LoadingState } from "@/components/ui/LoadingState";
import { Pagination } from "@/components/ui/Pagination";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { pageCount } from "@/lib/accounting";
import { formatDate } from "@/lib/balances";
import { formatAmount } from "@/lib/format";
import { STATUTS_VOLET, type ReconciliationFilter } from "@/lib/reconciliation";
import { listTransactions } from "@/services/reconciliation";
import type { Operation, OperationsPage } from "@/types/reconciliation";

type TransactionsPaneProps = {
  companyId: number;
  filter: ReconciliationFilter;
  reloadKey: number;
  selectedId: number | null;
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
  onSelect,
  onLoaded,
  statut,
  onStatutChange,
}: TransactionsPaneProps) {
  // Un statut changé depuis les compteurs repart de la première page
  const [shownStatut, setShownStatut] = useState(statut);
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<OperationsPage | null>(null);
  const [state, setState] = useState<"loading" | "error" | "ready">("loading");
  const [retryKey, setRetryKey] = useState(0);
  if (statut !== shownStatut) {
    setShownStatut(statut);
    setPage(1);
    setState("loading");
  }

  useEffect(() => {
    let cancelled = false;
    listTransactions(companyId, {
      ...filter,
      statut: statut || undefined,
      q,
      page,
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
  }, [companyId, filter, statut, q, page, reloadKey, retryKey, onLoaded]);

  const pages = data ? pageCount(data.total, data.taille) : 1;
  const columns: Column<Operation>[] = [
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
      render: (row) => formatAmount(row.debit, "DH", { dashForZero: true }),
    },
    {
      key: "credit",
      header: "Crédit",
      align: "right",
      render: (row) => formatAmount(row.credit, "DH", { dashForZero: true }),
    },
    { key: "statut", header: "Statut", render: (row) => <StatusBadge status={row.statut} /> },
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
        <div className="w-full max-w-[200px]">
          <Field label="Recherche" htmlFor="rapprochement-tx-recherche">
            <TextInput
              id="rapprochement-tx-recherche"
              value={search}
              maxLength={100}
              placeholder="Libellé, référence"
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
      </form>

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
            onRowClick={onSelect}
            isRowSelected={(row) => row.id === selectedId}
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
