"use client";

import { BookText, Search, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { BoutonFiltres, FiltresRepliables } from "@/components/rapprochement/FiltresRepliables";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { CodeBadge } from "@/components/rapprochement/CodeBadge";
import { PropositionBadge } from "@/components/rapprochement/PropositionBadge";
import { PiedDefilement } from "@/components/rapprochement/PiedDefilement";
import { useDefilement } from "@/components/rapprochement/useDefilement";
import { ErrorState } from "@/components/ui/ErrorState";
import { DateInput, Field, Select, TextInput } from "@/components/ui/Field";
import { LoadingState } from "@/components/ui/LoadingState";
import { StatusDot } from "@/components/ui/StatusBadge";
import { STATUTS_RAPPROCHEMENT } from "@/lib/accounting";
import { formatDate } from "@/lib/balances";
import { formatAmount } from "@/lib/format";
import type { ReconciliationFilter } from "@/lib/reconciliation";
import {
  avecDevise,
  bornerPeriode,
  dateCourte,
  montantVolet,
  SENS_VOLET,
  TYPES_OPERATION,
  unite,
} from "@/lib/reconciliation";
import { listEntries } from "@/services/accounting";
import type { Ecriture, EcrituresPage } from "@/types/accounting";

type EntriesPaneProps = {
  companyId: number;
  filter: ReconciliationFilter;
  reloadKey: number;
  /** Ligne dont le détail est ouvert. */
  selectedId: number | null;
  /** Lignes cochées (toujours, depuis le 28/10/2026) : le clic coche ou décoche. */
  coches: { ids: readonly number[]; onToggle: (row: Ecriture) => void };
  /** Clic sur une ligne rapprochée (non cochable) : son détail. */
  onSelect: (entry: Ecriture) => void;
  /** Lignes chargées : la vue met à jour l'écriture sélectionnée. */
  onLoaded: (entries: Ecriture[]) => void;
};

/**
 * Volet « Écritures comptables » : écritures Sage de la période (même compte), chargées 50 par 50
 * au défilement.
 * Débit et crédit au sens de Sage : un débit du compte banque correspond à un crédit en banque.
 */
export function EntriesPane({
  companyId,
  filter,
  reloadKey,
  selectedId,
  coches,
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
  const [retryKey, setRetryKey] = useState(0);

  const periode = bornerPeriode(filter, du, au);
  const filtresActifs = !!(statut || typeOperation || sens || du || au || q || search);
  const requete = {
    ...filter,
    from: periode.from,
    to: periode.to,
    statut: statut || undefined,
    q: q || undefined,
    typeOperation: typeOperation || undefined,
    sens: sens || undefined,
  };
  // Un filtre changé repart du haut
  const { etat, lu, suite, reste, chargerPlus } = useDefilement(
    JSON.stringify([companyId, requete]),
    `${reloadKey}|${retryKey}`,
    (page) => listEntries(companyId, { ...requete, page }),
    extraireEcritures,
  );

  useEffect(() => {
    if (lu) onLoaded(lu.lignes);
  }, [lu, onLoaded]);

  const colonnesBase: Column<Ecriture>[] = [
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
      key: "date_ecriture",
      header: "Date",
      // Échéance au survol de la date (28/10/2026)
      render: (row) => (
        <span
          className="whitespace-nowrap tabular-nums"
          title={
            row.echeance
              ? `${formatDate(row.date_ecriture)} · Échéance ${formatDate(row.echeance)}`
              : formatDate(row.date_ecriture)
          }
        >
          {dateCourte(row.date_ecriture)}
        </span>
      ),
    },
    {
      key: "libelle",
      header: "Libellé",
      render: (row) => (
        // Une seule ligne (27/10/2026) : libellé coupé, complet au survol, N° pièce (28/10/2026)
        // puis tiers à la suite
        <span
          className="flex max-w-[360px] min-w-[140px] items-baseline gap-2"
          title={[row.libelle, row.numero_piece ? `Pièce ${row.numero_piece}` : null, row.tiers]
            .filter(Boolean)
            .join(" · ")}
        >
          <span className="truncate">{row.libelle}</span>
          {row.numero_piece && (
            <span className="shrink-0 text-[11px] whitespace-nowrap text-simtis-muted">
              Pce {row.numero_piece}
            </span>
          )}
          {row.tiers && (
            <span className="shrink truncate text-[11px] text-simtis-muted">{row.tiers}</span>
          )}
          {row.statut === "À vérifier" && <PropositionBadge />}
        </span>
      ),
    },
    {
      key: "debit",
      header: "Débit (DH)",
      align: "right",
      render: (row) => montantVolet(row.debit),
    },
    {
      key: "credit",
      header: "Crédit (DH)",
      align: "right",
      render: (row) => montantVolet(row.credit),
    },
  ];
  // Colonne « Devise » seulement si la page contient un compte en devise (28/10/2026)
  const colonneDevise: Column<Ecriture>[] = [
    {
      key: "montant_devise",
      header: "Devise",
      align: "right",
      // Compte en devise : le montant qui se rapproche du relevé (14/10/2026)
      render: (row) =>
        row.montant_devise != null ? formatAmount(row.montant_devise, unite(row.devise)) : "-",
    },
  ];
  const columns: Column<Ecriture>[] = [
    ...colonnesBase,
    ...(lu && avecDevise(lu.lignes) ? colonneDevise : []),
    { key: "statut", header: "St.", render: (row) => <StatusDot status={row.statut} /> },
    { key: "code", header: "Code", render: (row) => <CodeBadge code={row.code_rapprochement} /> },
  ];

  return (
    <Card
      title="Écritures comptables"
      icon={BookText}
      compact
      headerExtra={
        <BoutonFiltres
          volet="ecritures"
          actifs={[statut, typeOperation, sens, du, au, q].filter(Boolean).length}
        />
      }
      className="xl:flex xl:h-[calc(100dvh-7rem)] xl:min-h-[480px] xl:flex-col"
    >
      <FiltresRepliables volet="ecritures">
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(event) => {
            event.preventDefault();
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
          message="Impossible de charger les écritures."
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
            emptyMessage="Aucune écriture sur ces critères."
            onRowClick={(row) =>
              row.statut === "Rapprochée" ? onSelect(row) : coches.onToggle(row)
            }
            isRowSelected={(row) => coches.ids.includes(row.id) || row.id === selectedId}
            rowLabel={(row) =>
              `Écriture du ${formatDate(row.date_ecriture)}, ${row.libelle}, ${row.statut}`
            }
            onScrollEnd={chargerPlus}
          />
          <PiedDefilement
            chargees={lu.lignes.length}
            total={lu.total}
            nom="écriture"
            suite={suite}
            reste={reste}
            onChargerPlus={chargerPlus}
          />
        </>
      )}
    </Card>
  );
}

function extraireEcritures(page: EcrituresPage) {
  return { total: page.total, lignes: page.ecritures };
}
