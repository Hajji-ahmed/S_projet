"use client";

import { BookText, Search } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { ErrorState } from "@/components/ui/ErrorState";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { LoadingState } from "@/components/ui/LoadingState";
import { Pagination } from "@/components/ui/Pagination";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { STATUTS_RAPPROCHEMENT, pageCount } from "@/lib/accounting";
import { formatDate } from "@/lib/balances";
import { formatAmount } from "@/lib/format";
import type { ReconciliationFilter } from "@/lib/reconciliation";
import { listEntries } from "@/services/accounting";
import type { Ecriture, EcrituresPage } from "@/types/accounting";

type EntriesPaneProps = {
  companyId: number;
  filter: ReconciliationFilter;
  reloadKey: number;
  selectedId: number | null;
  onSelect: (entry: Ecriture) => void;
  /** Chaque page chargée : la vue met à jour l'écriture sélectionnée. */
  onLoaded: (entries: Ecriture[]) => void;
};

/**
 * Volet « Écritures comptables » : écritures Sage de la période (même compte), 50 par page.
 * Débit et crédit au sens de Sage : un débit du compte banque correspond à un crédit en banque.
 */
export function EntriesPane({
  companyId,
  filter,
  reloadKey,
  selectedId,
  onSelect,
  onLoaded,
}: EntriesPaneProps) {
  const [statut, setStatut] = useState("");
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<EcrituresPage | null>(null);
  const [state, setState] = useState<"loading" | "error" | "ready">("loading");
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    listEntries(companyId, {
      ...filter,
      statut: statut || undefined,
      q: q || undefined,
      page,
    }).then(
      (result) => {
        if (cancelled) return;
        setData(result);
        setState("ready");
        onLoaded(result.ecritures);
      },
      () => {
        if (!cancelled) setState("error");
      },
    );
    return () => {
      cancelled = true;
    };
  }, [companyId, filter, statut, q, page, reloadKey, retryKey, onLoaded]);

  const pages = data ? pageCount(data.total, data.taille) : 1;
  const columns: Column<Ecriture>[] = [
    {
      key: "date_ecriture",
      header: "Date",
      render: (row) => <span className="whitespace-nowrap">{formatDate(row.date_ecriture)}</span>,
    },
    {
      key: "libelle",
      header: "Libellé",
      render: (row) => (
        <span className="block min-w-[160px]">
          <span className="block">{row.libelle}</span>
          {row.tiers && <span className="block text-xs text-simtis-muted">{row.tiers}</span>}
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
    {
      key: "numero_piece",
      header: "N° pièce",
      render: (row) => <span className="whitespace-nowrap">{row.numero_piece ?? "-"}</span>,
    },
    {
      key: "echeance",
      header: "Échéance",
      render: (row) => <span className="whitespace-nowrap">{formatDate(row.echeance)}</span>,
    },
    { key: "statut", header: "Statut", render: (row) => <StatusBadge status={row.statut} /> },
  ];

  return (
    <Card
      title="Écritures comptables"
      icon={BookText}
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
          <Field label="Statut" htmlFor="rapprochement-ec-statut">
            <Select
              id="rapprochement-ec-statut"
              value={statut}
              placeholder="Tous les statuts"
              options={STATUTS_RAPPROCHEMENT.map((item) => ({ value: item, label: item }))}
              onChange={(event) => {
                setState("loading");
                setPage(1);
                setStatut(event.target.value);
              }}
            />
          </Field>
        </div>
        <div className="w-full max-w-[200px]">
          <Field label="Recherche" htmlFor="rapprochement-ec-recherche">
            <TextInput
              id="rapprochement-ec-recherche"
              value={search}
              maxLength={100}
              placeholder="Libellé, pièce, tiers"
              onChange={(event) => setSearch(event.target.value)}
            />
          </Field>
        </div>
        <Button
          type="submit"
          variant="secondary"
          icon={Search}
          aria-label="Rechercher les écritures"
        >
          Rechercher
        </Button>
      </form>

      {state === "loading" && <LoadingState rows={5} />}
      {state === "error" && (
        <ErrorState
          message="Impossible de charger les écritures."
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
            rows={data.ecritures}
            getRowKey={(row) => String(row.id)}
            emptyMessage="Aucune écriture sur ces critères."
            onRowClick={onSelect}
            isRowSelected={(row) => row.id === selectedId}
            rowLabel={(row) =>
              `Écriture du ${formatDate(row.date_ecriture)}, ${row.libelle}, ${row.statut}`
            }
          />
          <Pagination
            label="Pages des écritures"
            page={data.page}
            pages={pages}
            total={data.total}
            noun="écriture"
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
