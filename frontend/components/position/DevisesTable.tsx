"use client";

import { Coins } from "lucide-react";

import { BankLabel } from "@/components/banks/BankLabel";
import {
  GRID_GREY,
  GRID_HEAD,
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
  COLONNES_DEVISES,
  LIGNES_DEVISES,
  cellKey,
  devisesToDraft,
  draftToDevisesInput,
} from "@/lib/saisies";
import { getDevises, saveDevises } from "@/services/saisies";
import type { Bank } from "@/types/bank";
import type { Devises, DevisesInput } from "@/types/saisie";

const API: GridApi<Devises, DevisesInput> = {
  load: getDevises,
  save: saveDevises,
  toDraft: devisesToDraft,
};

type DevisesTableProps = {
  companyId: number;
  jour: string;
  /** Colonnes de banques, dans l'ordre des tableaux (banques actives). */
  banks: Bank[];
  canEdit: boolean;
};

/**
 * Tableau Devises du classeur, saisi à la main : lignes EUR, USD et Exp DH convertible, cellules de
 * banques grisées, puis TOTAL et DEPASSEMENT. Rien n'y est calculé.
 */
export function DevisesTable({ companyId, jour, banks, canEdit }: DevisesTableProps) {
  const { toast } = useToast();
  const grid = useSaisieGrid(companyId, jour, API);

  async function save() {
    const parsed = draftToDevisesInput(
      grid.draft,
      banks.map((bank) => bank.id),
    );
    if (await grid.submit(parsed)) toast(`Tableau Devises du ${formatDate(jour)} enregistré.`);
  }

  function cell(key: string, label: string) {
    return (
      <GridCell
        label={label}
        value={grid.draft[key] ?? ""}
        onChange={(value) => grid.setCell(key, value)}
        readOnly={!canEdit}
        invalid={grid.invalid.includes(key)}
      />
    );
  }

  return (
    <Card title="Devises" icon={Coins}>
      {grid.loadState === "loading" && <LoadingState rows={3} />}
      {grid.loadState === "error" && (
        <ErrorState message="Impossible de charger le tableau Devises." onRetry={grid.retry} />
      )}
      {grid.loadState === "ready" && (
        <>
          <div className="overflow-x-auto">
            <table className={cn(GRID_TABLE, "min-w-[860px] table-fixed")} aria-label="Devises">
              <colgroup>
                <col className="w-[200px]" />
                {banks.map((bank) => (
                  <col key={bank.id} />
                ))}
                {COLONNES_DEVISES.map((column) => (
                  <col key={column.key} className="w-[130px]" />
                ))}
              </colgroup>
              <thead>
                <tr>
                  <th scope="col" className={GRID_HEAD}>
                    <span className="sr-only">Ligne</span>
                  </th>
                  {banks.map((bank) => (
                    <th key={bank.id} scope="col" className={GRID_HEAD}>
                      <BankLabel code={bank.code} logo={bank.logo} layout="stacked" />
                    </th>
                  ))}
                  {COLONNES_DEVISES.map((column) => (
                    <th key={column.key} scope="col" className={GRID_HEAD}>
                      {column.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {LIGNES_DEVISES.map((ligne) => (
                  <tr key={ligne}>
                    <th scope="row" className={GRID_HEAD}>
                      {ligne}
                    </th>
                    {banks.map((bank) => (
                      <td key={bank.id} className={cn("p-0", GRID_GREY)}>
                        {cell(cellKey(ligne, bank.id), `${ligne} ${bank.code}`)}
                      </td>
                    ))}
                    {COLONNES_DEVISES.map((column) => (
                      <td key={column.key} className="p-0">
                        {cell(cellKey(ligne, column.key), `${ligne} ${column.label}`)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {canEdit && (
            <GridFooter
              name="Devises"
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
