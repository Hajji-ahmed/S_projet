"use client";

import { ChevronUp, Landmark } from "lucide-react";
import { useEffect, useState } from "react";

import { BankLabel } from "@/components/banks/BankLabel";
import { GRID_FRAME, GRID_HEAD, GRID_ROW_HEAD, GRID_TABLE } from "@/components/position/GridCell";
import { PositionChart } from "@/components/position/PositionChart";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { formatDate } from "@/lib/balances";
import { cn } from "@/lib/cn";
import { formatAmount } from "@/lib/format";
import { JOURS_AFFICHES, formatJour, formatTaux, signTone, type Tone } from "@/lib/position";
import { showLast } from "@/lib/statements";
import { getBanquesTable } from "@/services/position";
import type { BanquesTable as Table, CelluleBanque, LigneBanques } from "@/types/position";

type LoadState = "loading" | "error" | "ready";

const NUMBER = "px-3 py-2.5 text-right tabular-nums whitespace-nowrap";
const ROW_HEAD = GRID_ROW_HEAD;
const GRID = cn(GRID_TABLE, "min-w-[860px] table-fixed");
// Disponible Fc reel : vert > 0, rouge < 0 (tokens de statut, pas le vert du classeur)
const TONES: Record<Tone, string> = {
  positive: "text-simtis-success",
  negative: "text-simtis-danger",
  neutral: "",
};

type BanquesTableProps = {
  companyId: number;
  /** Date de fin du tableau (« AAAA-MM-JJ ») ; l'API ne va jamais au-delà d'aujourd'hui. */
  jour: string;
};

/**
 * Tableau Banques du classeur, calculé par l'API à partir des soldes du jour (lecture seule) :
 * Taux, LIGNE, une ligne « facilité de caisse » par jour (solde + LIGNE), Disponible Fc reel.
 */
export function BanquesTable({ companyId, jour }: BanquesTableProps) {
  const [table, setTable] = useState<Table | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [retryKey, setRetryKey] = useState(0);
  const [shown, setShown] = useState(JOURS_AFFICHES);

  useEffect(() => {
    let cancelled = false;
    getBanquesTable(companyId, jour).then(
      (result) => {
        if (cancelled) return;
        setTable(result);
        setState("ready");
      },
      () => {
        if (!cancelled) setState("error");
      },
    );
    return () => {
      cancelled = true;
    };
  }, [companyId, jour, retryKey]);

  return (
    <>
      <Card title="Banques" icon={Landmark}>
        {state === "loading" && <LoadingState rows={4} />}
        {state === "error" && (
          <ErrorState
            message="Impossible de charger le tableau Banques."
            onRetry={() => {
              setState("loading");
              setRetryKey((key) => key + 1);
            }}
          />
        )}
        {state === "ready" && table && (
          <Grid
            table={table}
            shown={shown}
            onShowMore={() => setShown((count) => count + JOURS_AFFICHES)}
          />
        )}
      </Card>
      {/* P8.3 : mêmes données que le tableau, sans second appel à l'API */}
      {state === "ready" && table && <PositionChart jours={table.jours} banques={table.banques} />}
    </>
  );
}

function Grid({
  table,
  shown,
  onShowMore,
}: {
  table: Table;
  shown: number;
  onShowMore: () => void;
}) {
  // Les jours les plus récents d'abord visibles ; ordre du classeur : le plus ancien en haut
  const visible = showLast(table.jours, shown, JOURS_AFFICHES);

  return (
    <>
      {visible.hidden > 0 && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-sm">
          <p className="text-simtis-muted">
            {visible.rows.length} derniers jours sur {table.jours.length}
          </p>
          <Button
            variant="ghost"
            icon={ChevronUp}
            onClick={onShowMore}
            className="h-auto min-h-10 px-0 whitespace-normal"
          >
            Afficher {visible.next} {visible.next > 1 ? "jours plus anciens" : "jour plus ancien"}
          </Button>
        </div>
      )}
      {/* GRID_FRAME est relative : le texte des lecteurs d'écran ne doit pas élargir la page */}
      <div className={GRID_FRAME}>
        <table className={GRID} aria-label="Banques">
          <colgroup>
            <col className="w-[200px]" />
            {table.banques.map((banque) => (
              <col key={banque.bank_id} />
            ))}
            <col className="w-[130px]" />
            <col className="w-[130px]" />
          </colgroup>
          <thead>
            <tr>
              <th scope="col" className={cn(GRID_HEAD, "text-left")}>
                Banque
              </th>
              {table.banques.map((banque) => (
                <th key={banque.bank_id} scope="col" className={GRID_HEAD}>
                  <BankLabel code={banque.code} logo={banque.logo} layout="stacked" />
                </th>
              ))}
              <th scope="col" className={GRID_HEAD}>
                TOTAL
              </th>
              <th scope="col" className={GRID_HEAD}>
                DEPASSEMENT
              </th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row" className={ROW_HEAD}>
                Taux
              </th>
              {table.banques.map((banque) => (
                <td key={banque.bank_id} className={NUMBER}>
                  {formatTaux(banque.taux_pct)}
                </td>
              ))}
              <td />
              <td />
            </tr>
            <tr>
              <th
                scope="row"
                className={ROW_HEAD}
                title="LIGNE actuelle du compte, appliquée à tous les jours"
              >
                LIGNE
              </th>
              {table.banques.map((banque) => (
                <td key={banque.bank_id} className={NUMBER}>
                  {formatAmount(banque.ligne)}
                </td>
              ))}
              <td className={NUMBER}>{formatAmount(table.ligne_total)}</td>
              <td />
            </tr>
            {visible.rows.map((day) => (
              <tr key={day.date}>
                <th scope="row" className={ROW_HEAD}>
                  facilité de caisse <span className="tabular-nums">{formatJour(day.date)}</span>
                </th>
                <LineCells line={day} />
              </tr>
            ))}
          </tbody>
          {/* Ligne séparée sous le tableau, mais dans le même tableau : elle défile avec lui et
              garde les en-têtes de colonnes (lecteurs d'écran). La rangée vide la détache. */}
          <tbody>
            <tr aria-hidden="true">
              <td
                colSpan={table.banques.length + 3}
                className="h-3 border-x-0! border-b-0! bg-simtis-card p-0"
              />
            </tr>
            {/* Comme la ligne Total des autres tableaux : semi-gras sur fond gris très clair */}
            <tr className="bg-simtis-background font-semibold">
              <th scope="row" className={ROW_HEAD}>
                Disponible Fc reel
              </th>
              <LineCells line={table.disponible} colored />
            </tr>
          </tbody>
        </table>
      </div>
      {table.jours.length === 0 && (
        <p className="mt-3 text-sm text-simtis-muted">Aucun solde enregistré pour cette société.</p>
      )}
    </>
  );
}

function LineCells({ line, colored = false }: { line: LigneBanques; colored?: boolean }) {
  const tone = (value: string | null) => (colored ? TONES[signTone(value)] : "");
  return (
    <>
      {line.cellules.map((cellule) => (
        <AmountCell key={cellule.bank_id} cellule={cellule} className={tone(cellule.valeur)} />
      ))}
      <td className={cn(NUMBER, tone(line.total))}>{formatAmount(line.total)}</td>
      <td className={cn(NUMBER, tone(line.depassement))}>{formatAmount(line.depassement)}</td>
    </>
  );
}

/** Montant d'une banque ; un solde repris d'un jour précédent est grisé et daté. */
function AmountCell({ cellule, className }: { cellule: CelluleBanque; className: string }) {
  if (!cellule.reprise) {
    return <td className={cn(NUMBER, className)}>{formatAmount(cellule.valeur)}</td>;
  }
  const note = `dernier solde connu : ${formatDate(cellule.date_solde)}`;
  return (
    <td className={cn(NUMBER, "text-simtis-muted", className)} title={note}>
      {formatAmount(cellule.valeur)}
      <span className="sr-only"> ({note})</span>
    </td>
  );
}
