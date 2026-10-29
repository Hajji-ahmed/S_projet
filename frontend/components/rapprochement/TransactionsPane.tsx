"use client";

import { Landmark } from "lucide-react";
import { useEffect, useState } from "react";

import { Card } from "@/components/ui/Card";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { CodeBadge } from "@/components/rapprochement/CodeBadge";
import {
  ChoixFiltre,
  EffacerFiltres,
  FiltreColonne,
  FiltreDates,
  FiltreLibelle,
  FiltreSens,
} from "@/components/rapprochement/FiltreColonne";
import { PropositionBadge } from "@/components/rapprochement/PropositionBadge";
import { PiedDefilement } from "@/components/rapprochement/PiedDefilement";
import { useDefilement } from "@/components/rapprochement/useDefilement";
import { EnCoursBadge } from "@/components/releves/EnCoursBadge";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { StatusDot } from "@/components/ui/StatusBadge";
import { formatDate } from "@/lib/balances";
import { cn } from "@/lib/cn";
import {
  bornerPeriode,
  colonnesFiltrees,
  dateCourte,
  FILTRES_VIDES,
  filtresActifs,
  montantVolet,
  STATUTS_VOLET,
  type FiltresVolet,
  type ReconciliationFilter,
} from "@/lib/reconciliation";
import { listTransactions } from "@/services/reconciliation";
import type { Operation, OperationsPage } from "@/types/reconciliation";

type TransactionsPaneProps = {
  /** Plein écran (29/10/2026) : le volet remplit la fenêtre sous le bandeau. */
  pleinEcran?: boolean;
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
 * cochées au clic, filtrées depuis les en-têtes de colonnes (28/10/2026). */
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
  pleinEcran = false,
}: TransactionsPaneProps) {
  // Dates, libellé, type et sens propres au volet ; le statut vient de la vue (compteurs)
  const [autres, setAutres] = useState<FiltresVolet>(FILTRES_VIDES);
  const [retryKey, setRetryKey] = useState(0);
  const filtres: FiltresVolet = { ...autres, statut };
  const allumees = colonnesFiltrees(filtres);
  const changer = (modif: Partial<FiltresVolet>) => setAutres((avant) => ({ ...avant, ...modif }));

  const periode = bornerPeriode(filter, filtres.du, filtres.au);
  const requete = {
    ...filter,
    from: periode.from,
    to: periode.to,
    statut: statut || undefined,
    q: filtres.q,
    typeOperation: filtres.typeOperation || undefined,
    sens: filtres.sens || undefined,
  };
  // Un filtre changé (ici ou par les compteurs de la vue) repart du haut
  const { etat, lu, affiche, suite, reste, chargerPlus } = useDefilement(
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
      filtre: (
        <FiltreColonne colonne="Date" actif={allumees.date}>
          {(fermer) => (
            <FiltreDates
              id="rapprochement-tx-dates"
              du={filtres.du}
              au={filtres.au}
              min={filter.from}
              max={filter.to}
              onAppliquer={(du, au) => {
                changer({ du, au });
                fermer();
              }}
            />
          )}
        </FiltreColonne>
      ),
      render: (row) => (
        <span className="whitespace-nowrap tabular-nums" title={formatDate(row.date_operation)}>
          {dateCourte(row.date_operation)}
        </span>
      ),
    },
    {
      key: "libelle",
      header: "Libellé",
      filtre: (
        <FiltreColonne colonne="Libellé" actif={allumees.libelle}>
          {() => (
            <FiltreLibelle
              id="rapprochement-tx-libelle"
              filtres={filtres}
              placeholder="Libellé, référence, code"
              onChanger={changer}
            />
          )}
        </FiltreColonne>
      ),
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
      filtre: (
        <FiltreSens
          colonne="Débit"
          actif={allumees.debit}
          sens={filtres.sens}
          onChanger={changer}
        />
      ),
      render: (row) => montantVolet(row.debit, row.devise),
    },
    {
      key: "credit",
      header: "Crédit (DH)",
      align: "right",
      filtre: (
        <FiltreSens
          colonne="Crédit"
          actif={allumees.credit}
          sens={filtres.sens}
          onChanger={changer}
        />
      ),
      render: (row) => montantVolet(row.credit, row.devise),
    },
    {
      key: "statut",
      header: "St.",
      filtre: (
        <FiltreColonne colonne="Statut" actif={allumees.statut}>
          {(fermer) => (
            <ChoixFiltre
              titre="Statut"
              options={[
                { value: "", label: "Tous les statuts" },
                ...STATUTS_VOLET.map((item) => ({ value: item, label: item })),
              ]}
              valeur={statut}
              onChoisir={(valeur) => {
                onStatutChange(valeur);
                fermer();
              }}
            />
          )}
        </FiltreColonne>
      ),
      render: (row) => <StatusDot status={row.statut} />,
    },
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
        <EffacerFiltres
          visible={filtresActifs(filtres)}
          onEffacer={() => {
            onStatutChange("");
            setAutres(FILTRES_VIDES);
          }}
        />
      }
      className={cn(
        "xl:flex xl:min-h-[480px] xl:flex-col",
        pleinEcran
          ? "xl:h-[calc(100dvh-var(--hauteur-bandeau)-1.75rem)]"
          : "xl:h-[calc(100dvh-7rem)]",
      )}
    >
      {periode.ajustee && (
        <p className="mb-2 text-xs text-simtis-warning-fg">
          Dates ramenées à la période de l&apos;écran ({formatDate(filter.from)} au{" "}
          {formatDate(filter.to)}).
        </p>
      )}

      {etat === "error" ? (
        <ErrorState
          message="Impossible de charger les opérations."
          onRetry={() => setRetryKey((key) => key + 1)}
        />
      ) : affiche ? (
        // Le tableau reste affiché (grisé) pendant qu'un filtre se charge : ses en-têtes portent
        // les filtres
        <>
          <DataTable
            stickyHeader
            dense
            className={cn(
              "transition-opacity xl:min-h-0 xl:flex-1 xl:overflow-y-auto",
              etat === "loading" && "opacity-60",
            )}
            columns={columns}
            rows={affiche.lignes}
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
            chargees={affiche.lignes.length}
            total={affiche.total}
            nom="opération"
            suite={suite}
            reste={reste}
            onChargerPlus={chargerPlus}
          />
        </>
      ) : (
        <LoadingState rows={5} />
      )}
    </Card>
  );
}

function extraireOperations(page: OperationsPage) {
  return { total: page.total, lignes: page.operations };
}
