"use client";

import { CalendarClock } from "lucide-react";

import { BankLabel } from "@/components/banks/BankLabel";
import {
  GRID_FRAME,
  GRID_GREY,
  GRID_HEAD,
  GRID_ROW_HEAD,
  GRID_TABLE,
  GridCell,
  GridFooter,
} from "@/components/position/GridCell";
import { useSaisieGrid, type GridApi } from "@/components/position/useSaisieGrid";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { useToast } from "@/components/ui/Toast";
import { formatDate } from "@/lib/balances";
import { cn } from "@/lib/cn";
import {
  COLONNES_JOUR,
  LIBELLE_MAX,
  LIGNES_PREVISIONS,
  NB_LIGNES_PREVISIONS,
  cellKey,
  draftToPrevisionsInput,
  previsionsToDraft,
} from "@/lib/saisies";
import { getPrevisions, savePrevisions } from "@/services/saisies";
import type { Bank } from "@/types/bank";
import type { Previsions, PrevisionsInput } from "@/types/saisie";

const API: GridApi<Previsions, PrevisionsInput> = {
  load: getPrevisions,
  save: savePrevisions,
  toDraft: previsionsToDraft,
};

type PrevisionsTableProps = {
  companyId: number;
  jour: string;
  /** Colonnes de banques, dans l'ordre des tableaux (banques actives). */
  banks: Bank[];
  canEdit: boolean;
};

/**
 * Tableau Prévisions du classeur, saisi à la main : la date fusionnée à gauche sur les 14 lignes, un
 * libellé et un montant par banque sur chaque ligne, puis Encaissement, Escompte et Douane, une
 * cellule par ligne (décision du 03/10/2026). Rien n'y est calculé.
 */
export function PrevisionsTable({ companyId, jour, banks, canEdit }: PrevisionsTableProps) {
  const { toast } = useToast();
  const grid = useSaisieGrid(companyId, jour, API);

  async function save() {
    const parsed = draftToPrevisionsInput(
      grid.draft,
      banks.map((bank) => bank.id),
    );
    if (await grid.submit(parsed)) toast(`Tableau Prévisions du ${formatDate(jour)} enregistré.`);
  }

  function cell(key: string, label: string, text = false) {
    return (
      <GridCell
        label={label}
        value={grid.draft[key] ?? ""}
        onChange={(value) => grid.setCell(key, value)}
        readOnly={!canEdit}
        invalid={grid.invalid.includes(key)}
        align={text ? "left" : "right"}
        maxLength={text ? LIBELLE_MAX : undefined}
      />
    );
  }

  return (
    <Card title="Prévisions" icon={CalendarClock}>
      {grid.loadState === "loading" && <LoadingState rows={6} />}
      {grid.loadState === "error" && (
        <ErrorState message="Impossible de charger le tableau Prévisions." onRetry={grid.retry} />
      )}
      {grid.loadState === "ready" && (
        <>
          <div className={GRID_FRAME}>
            <table className={cn(GRID_TABLE, "min-w-[1000px] table-fixed")} aria-label="Prévisions">
              <colgroup>
                <col className="w-[110px]" />
                <col className="w-[180px]" />
                {banks.map((bank) => (
                  <col key={bank.id} />
                ))}
                {COLONNES_JOUR.map((column) => (
                  <col key={column.key} className="w-[120px]" />
                ))}
              </colgroup>
              <thead>
                <tr>
                  <th scope="col" className={GRID_HEAD}>
                    <span className="sr-only">Date</span>
                  </th>
                  <th scope="col" className={GRID_HEAD}>
                    <span className="sr-only">Libellé</span>
                  </th>
                  {banks.map((bank) => (
                    <th key={bank.id} scope="col" className={GRID_HEAD}>
                      <BankLabel code={bank.code} logo={bank.logo} layout="stacked" />
                    </th>
                  ))}
                  {COLONNES_JOUR.map((column) => (
                    <th
                      key={column.key}
                      scope="col"
                      className={cn(GRID_HEAD, GRID_GREY, "text-left")}
                    >
                      {column.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {LIGNES_PREVISIONS.map((ligne) => (
                  <tr key={ligne}>
                    {ligne === 1 && (
                      <th
                        scope="rowgroup"
                        rowSpan={NB_LIGNES_PREVISIONS}
                        className={cn(GRID_ROW_HEAD, "text-center align-middle")}
                      >
                        {formatDate(jour)}
                      </th>
                    )}
                    <td className="p-0">
                      {cell(cellKey(ligne, "libelle"), `Ligne ${ligne} libellé`, true)}
                    </td>
                    {banks.map((bank) => (
                      <td key={bank.id} className="p-0">
                        {cell(cellKey(ligne, bank.id), `Ligne ${ligne} ${bank.code}`)}
                      </td>
                    ))}
                    {/* Une cellule par ligne (décision du 03/10/2026), comme les banques */}
                    {COLONNES_JOUR.map((column) => (
                      <td key={column.key} className="p-0">
                        {cell(cellKey(ligne, column.key), `Ligne ${ligne} ${column.label}`)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {canEdit && (
            <GridFooter
              name="Prévisions"
              dirty={grid.dirty}
              saving={grid.saving}
              invalidCount={grid.invalid.length}
              error={grid.error}
              onReset={grid.reset}
              onSave={save}
            />
          )}
        </>
      )}
    </Card>
  );
}
