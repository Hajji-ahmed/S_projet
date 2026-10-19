"use client";

import { BookText, Search, X } from "lucide-react";
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
import { STATUTS_RAPPROCHEMENT, pageCount } from "@/lib/accounting";
import { formatDate } from "@/lib/balances";
import { formatAmount } from "@/lib/format";
import type { ReconciliationFilter } from "@/lib/reconciliation";
import { bornerPeriode, SENS_VOLET, TYPES_OPERATION, unite } from "@/lib/reconciliation";
import { listEntries } from "@/services/accounting";
import type { Ecriture, EcrituresPage } from "@/types/accounting";

type EntriesPaneProps = {
  companyId: number;
  filter: ReconciliationFilter;
  reloadKey: number;
  selectedId: number | null;
  /** Sélection multiple (P13, 15/10/2026) : une case par ligne, le clic coche ou décoche. */
  multi?: { ids: readonly number[]; onToggle: (row: Ecriture) => void };
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
  multi,
  onSelect,
  onLoaded,
}: EntriesPaneProps) {
  const [statut, setStatut] = useState("");
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [typeOperation, setTypeOperation] = useState("");
  // Sens et dates propres au volet (19/10/2026)
  const [sens, setSens] = useState("");
  const [du, setDu] = useState("");
  const [au, setAu] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<EcrituresPage | null>(null);
  const [state, setState] = useState<"loading" | "error" | "ready">("loading");
  const [retryKey, setRetryKey] = useState(0);

  const periode = bornerPeriode(filter, du, au);
  const filtresActifs = !!(statut || typeOperation || sens || du || au || q || search);

  useEffect(() => {
    let cancelled = false;
    listEntries(companyId, {
      ...filter,
      from: periode.from,
      to: periode.to,
      statut: statut || undefined,
      q: q || undefined,
      typeOperation: typeOperation || undefined,
      sens: sens || undefined,
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
  const caseColumn: Column<Ecriture>[] = multi
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
  const columns: Column<Ecriture>[] = [
    ...caseColumn,
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
      key: "montant_devise",
      header: "Devise",
      align: "right",
      // Compte en devise : le montant qui se rapproche du relevé (14/10/2026)
      render: (row) =>
        row.montant_devise != null ? formatAmount(row.montant_devise, unite(row.devise)) : "-",
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
    { key: "code", header: "Code", render: (row) => <CodeBadge code={row.code_rapprochement} /> },
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
        <div className="w-full max-w-[150px]">
          <Field label="Type" htmlFor="rapprochement-ec-type">
            <Select
              id="rapprochement-ec-type"
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
          <Field label="Sens" htmlFor="rapprochement-ec-sens">
            <Select
              id="rapprochement-ec-sens"
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
          <Field label="Du" htmlFor="rapprochement-ec-du">
            <DateInput
              id="rapprochement-ec-du"
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
          <Field label="Au" htmlFor="rapprochement-ec-au">
            <DateInput
              id="rapprochement-ec-au"
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
          <Field label="Recherche" htmlFor="rapprochement-ec-recherche">
            <TextInput
              id="rapprochement-ec-recherche"
              value={search}
              maxLength={100}
              placeholder="Libellé, pièce, tiers, code"
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
        <Button
          type="button"
          variant="ghost"
          icon={X}
          disabled={!filtresActifs}
          onClick={() => {
            setState("loading");
            setPage(1);
            setStatut("");
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
            onRowClick={multi ? multi.onToggle : onSelect}
            isRowSelected={(row) => (multi ? multi.ids.includes(row.id) : row.id === selectedId)}
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
