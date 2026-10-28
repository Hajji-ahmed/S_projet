"use client";

import { BookText } from "lucide-react";
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
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { StatusDot } from "@/components/ui/StatusBadge";
import { STATUTS_RAPPROCHEMENT } from "@/lib/accounting";
import { formatDate } from "@/lib/balances";
import { cn } from "@/lib/cn";
import { formatAmount } from "@/lib/format";
import {
  avecDevise,
  bornerPeriode,
  colonnesFiltrees,
  dateCourte,
  FILTRES_VIDES,
  filtresActifs,
  montantVolet,
  unite,
  type FiltresVolet,
  type ReconciliationFilter,
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
 * au défilement, filtrées depuis les en-têtes de colonnes (28/10/2026).
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
  const [filtres, setFiltres] = useState<FiltresVolet>(FILTRES_VIDES);
  const [retryKey, setRetryKey] = useState(0);
  const allumees = colonnesFiltrees(filtres);
  const changer = (modif: Partial<FiltresVolet>) => setFiltres((avant) => ({ ...avant, ...modif }));

  const periode = bornerPeriode(filter, filtres.du, filtres.au);
  const requete = {
    ...filter,
    from: periode.from,
    to: periode.to,
    statut: filtres.statut || undefined,
    q: filtres.q || undefined,
    typeOperation: filtres.typeOperation || undefined,
    sens: filtres.sens || undefined,
  };
  // Un filtre changé repart du haut
  const { etat, lu, affiche, suite, reste, chargerPlus } = useDefilement(
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
      filtre: (
        <FiltreColonne colonne="Date" actif={allumees.date}>
          {(fermer) => (
            <FiltreDates
              id="rapprochement-ec-dates"
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
      filtre: (
        <FiltreColonne colonne="Libellé" actif={allumees.libelle}>
          {() => (
            <FiltreLibelle
              id="rapprochement-ec-libelle"
              filtres={filtres}
              placeholder="Libellé, pièce, tiers, code"
              onChanger={changer}
            />
          )}
        </FiltreColonne>
      ),
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
      filtre: (
        <FiltreSens
          colonne="Débit"
          actif={allumees.debit}
          sens={filtres.sens}
          onChanger={changer}
        />
      ),
      render: (row) => montantVolet(row.debit),
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
    ...(affiche && avecDevise(affiche.lignes) ? colonneDevise : []),
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
                ...STATUTS_RAPPROCHEMENT.map((item) => ({ value: item, label: item })),
              ]}
              valeur={filtres.statut}
              onChoisir={(statut) => {
                changer({ statut });
                fermer();
              }}
            />
          )}
        </FiltreColonne>
      ),
      render: (row) => <StatusDot status={row.statut} />,
    },
    { key: "code", header: "Code", render: (row) => <CodeBadge code={row.code_rapprochement} /> },
  ];

  return (
    <Card
      title="Écritures comptables"
      icon={BookText}
      compact
      headerExtra={
        <EffacerFiltres
          visible={filtresActifs(filtres)}
          onEffacer={() => setFiltres(FILTRES_VIDES)}
        />
      }
      className="xl:flex xl:h-[calc(100dvh-7rem)] xl:min-h-[480px] xl:flex-col"
    >
      {periode.ajustee && (
        <p className="mb-2 text-xs text-simtis-warning-fg">
          Dates ramenées à la période de l&apos;écran ({formatDate(filter.from)} au{" "}
          {formatDate(filter.to)}).
        </p>
      )}

      {etat === "error" ? (
        <ErrorState
          message="Impossible de charger les écritures."
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
            chargees={affiche.lignes.length}
            total={affiche.total}
            nom="écriture"
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

function extraireEcritures(page: EcrituresPage) {
  return { total: page.total, lignes: page.ecritures };
}
