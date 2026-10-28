"use client";

import { Landmark, Search, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { BoutonFiltres, FiltresRepliables } from "@/components/rapprochement/FiltresRepliables";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { CodeBadge } from "@/components/rapprochement/CodeBadge";
import { PropositionBadge } from "@/components/rapprochement/PropositionBadge";
import { PiedDefilement } from "@/components/rapprochement/PiedDefilement";
import { useDefilement } from "@/components/rapprochement/useDefilement";
import { EnCoursBadge } from "@/components/releves/EnCoursBadge";
import { ErrorState } from "@/components/ui/ErrorState";
import { DateInput, Field, Select, TextInput } from "@/components/ui/Field";
import { LoadingState } from "@/components/ui/LoadingState";
import { StatusDot } from "@/components/ui/StatusBadge";
import { formatDate } from "@/lib/balances";
import {
  bornerPeriode,
  dateCourte,
  montantVolet,
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
  /** Ligne dont le détail est ouvert. */
  selectedId: number | null;
  /** Lignes cochées (toujours, depuis le 28/10/2026) : le clic coche ou décoche. */
  coches: { ids: readonly number[]; onToggle: (row: Operation) => void };
  /** Clic sur une ligne rapprochée (non cochable) : son détail. */
  onSelect: (operation: Operation) => void;
  /** Filtre Statut, piloté aussi par les compteurs de la vue ("" = tous les statuts). */
  statut: string;
  onStatutChange: (statut: string) => void;
  /** Lignes chargées (compteurs de la première page) : la vue met à jour la sélection et le
   * résumé. */
  onLoaded: (page: OperationsPage) => void;
};

/** Volet « Transactions bancaires » : opérations de la période, chargées 50 par 50 au défilement,
 * cochées au clic. */
export function TransactionsPane({
  companyId,
  filter,
  reloadKey,
  selectedId,
  coches,
  onSelect,
  onLoaded,
  statut,
  onStatutChange,
}: TransactionsPaneProps) {
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [typeOperation, setTypeOperation] = useState("");
  // Sens et dates propres au volet (19/10/2026)
  const [sens, setSens] = useState("");
  const [du, setDu] = useState("");
  const [au, setAu] = useState("");
  const [retryKey, setRetryKey] = useState(0);

  const periode = bornerPeriode(filter, du, au);
  const filtresActifs = !!(statut || typeOperation || sens || du || au || q || search);
  const requete = {
    ...filter,
    from: periode.from,
    to: periode.to,
    statut: statut || undefined,
    q,
    typeOperation: typeOperation || undefined,
    sens: sens || undefined,
  };
  // Un filtre changé (ici ou par les compteurs de la vue) repart du haut
  const { etat, lu, suite, reste, chargerPlus } = useDefilement(
    JSON.stringify([companyId, requete]),
    `${reloadKey}|${retryKey}`,
    (page) => listTransactions(companyId, { ...requete, page }),
    extraireOperations,
  );

  useEffect(() => {
    if (lu) onLoaded({ ...lu.premiere, operations: lu.lignes });
  }, [lu, onLoaded]);

  const columns: Column<Operation>[] = [
    {
      key: "choisie",
      header: "",
      render: (row) => (
        <input
          type="checkbox"
          readOnly
          tabIndex={-1}
          checked={coches.ids.includes(row.id)}
          disabled={row.statut === "Rapprochée"}
          aria-label={`Choisir ${row.libelle}`}
          className="pointer-events-none h-3.5 w-3.5 accent-simtis-primary"
        />
      ),
    },
    {
      key: "date_operation",
      header: "Date",
      render: (row) => (
        <span className="whitespace-nowrap tabular-nums" title={formatDate(row.date_operation)}>
          {dateCourte(row.date_operation)}
        </span>
      ),
    },
    {
      key: "libelle",
      header: "Libellé",
      render: (row) => (
        // Une seule ligne (27/10/2026) : libellé coupé, complet au survol, Réf. à la suite
        <span
          className="flex max-w-[360px] min-w-[140px] items-baseline gap-2"
          title={row.reference ? `${row.libelle} · Réf. ${row.reference}` : row.libelle}
        >
          <span className="truncate">{row.libelle}</span>
          {row.reference && (
            <span className="shrink-0 text-[11px] text-simtis-muted">Réf. {row.reference}</span>
          )}
          {row.en_cours && <EnCoursBadge />}
          {row.statut === "À vérifier" && <PropositionBadge />}
        </span>
      ),
    },
    {
      key: "debit",
      header: "Débit (DH)",
      align: "right",
      render: (row) => montantVolet(row.debit, row.devise),
    },
    {
      key: "credit",
      header: "Crédit (DH)",
      align: "right",
      render: (row) => montantVolet(row.credit, row.devise),
    },
    { key: "statut", header: "St.", render: (row) => <StatusDot status={row.statut} /> },
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
      compact
      headerExtra={
        <BoutonFiltres
          volet="operations"
          actifs={[statut, typeOperation, sens, du, au, q].filter(Boolean).length}
        />
      }
      className="xl:flex xl:h-[calc(100dvh-7rem)] xl:min-h-[480px] xl:flex-col"
    >
      <FiltresRepliables volet="operations">
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(event) => {
            event.preventDefault();
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
      </FiltresRepliables>
      {periode.ajustee && (
        <p className="-mt-2 mb-3 text-xs text-simtis-warning-fg">
          Dates ramenées à la période de l&apos;écran ({formatDate(filter.from)} au{" "}
          {formatDate(filter.to)}).
        </p>
      )}

      {etat === "loading" && <LoadingState rows={5} />}
      {etat === "error" && (
        <ErrorState
          message="Impossible de charger les opérations."
          onRetry={() => setRetryKey((key) => key + 1)}
        />
      )}
      {etat === "ready" && lu && (
        <>
          <DataTable
            stickyHeader
            dense
            className="xl:min-h-0 xl:flex-1 xl:overflow-y-auto"
            columns={columns}
            rows={lu.lignes}
            getRowKey={(row) => String(row.id)}
            emptyMessage="Aucune opération sur ces critères."
            onRowClick={(row) =>
              row.statut === "Rapprochée" ? onSelect(row) : coches.onToggle(row)
            }
            isRowSelected={(row) => coches.ids.includes(row.id) || row.id === selectedId}
            rowLabel={(row) =>
              `Opération du ${formatDate(row.date_operation)}, ${row.libelle}, ${row.statut}`
            }
            onScrollEnd={chargerPlus}
          />
          <PiedDefilement
            chargees={lu.lignes.length}
            total={lu.total}
            nom="opération"
            suite={suite}
            reste={reste}
            onChargerPlus={chargerPlus}
          />
        </>
      )}
    </Card>
  );
}

function extraireOperations(page: OperationsPage) {
  return { total: page.total, lignes: page.operations };
}
