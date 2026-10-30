"use client";

import { CalendarClock, Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { BankLabel } from "@/components/banks/BankLabel";
import {
  largeurMin,
  GRID_FRAME,
  GRID_GREY,
  GRID_HEAD,
  GRID_ROW_HEAD,
  GRID_TABLE,
  GridCell,
  GridFooter,
} from "@/components/position/GridCell";
import { useSaisieGrid, type GridApi } from "@/components/position/useSaisieGrid";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { DateInput } from "@/components/ui/Field";
import { LoadingState } from "@/components/ui/LoadingState";
import { useToast } from "@/components/ui/Toast";
import { formatDate } from "@/lib/balances";
import { cn } from "@/lib/cn";
import {
  COLONNES_JOUR,
  LIBELLE_MAX,
  LIGNES_PAR_DATE_MAX,
  ajouterLigne,
  cellKey,
  draftToPrevisionsInput,
  groupesParDate,
  lignesPrevisions,
  previsionsToDraft,
  supprimerLigne,
} from "@/lib/saisies";
import { getPrevisions, savePrevisions } from "@/services/saisies";
import type { Bank } from "@/types/bank";
import type { Previsions, PrevisionsInput } from "@/types/saisie";

const API: GridApi<Previsions, PrevisionsInput> = {
  load: getPrevisions,
  save: savePrevisions,
  toDraft: previsionsToDraft,
};

const ICON_BUTTON =
  "rounded-md p-1 text-simtis-muted transition-colors duration-150 disabled:pointer-events-none disabled:opacity-40";

type PrevisionsTableProps = {
  companyId: number;
  jour: string;
  /** Colonnes de banques, dans l'ordre des tableaux (banques actives). */
  banks: Bank[];
  canEdit: boolean;
};

/**
 * Tableau Prévisions, saisi à la main : chaque ligne a sa date (décision du 30/10/2026), fusionnée à
 * gauche sur les lignes de la même date ; un libellé et un montant par banque, puis Encaissement,
 * Escompte et Douane. Le tableau montre les lignes datées du jour choisi ou plus tard ; la Trésorerie
 * ajoute une ligne (à une nouvelle date ou sous une date existante) ou la supprime, puis enregistre.
 * Rien n'y est calculé.
 */
export function PrevisionsTable({ companyId, jour, banks, canEdit }: PrevisionsTableProps) {
  const { toast } = useToast();
  const grid = useSaisieGrid(companyId, jour, API);
  const [nouvelleDate, setNouvelleDate] = useState(jour);
  const groupes = groupesParDate(lignesPrevisions(grid.draft));
  const pleine = (date: string) =>
    (groupes.find((groupe) => groupe.jour === date)?.lignes.length ?? 0) >= LIGNES_PAR_DATE_MAX;
  const dateValide = nouvelleDate >= jour && !pleine(nouvelleDate);

  async function save() {
    const parsed = draftToPrevisionsInput(
      grid.draft,
      banks.map((bank) => bank.id),
    );
    if (await grid.submit(parsed)) toast("Tableau Prévisions enregistré.");
  }

  function ajouter(date: string) {
    grid.changeDraft((draft) => ajouterLigne(draft, date));
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
        formule={!text}
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
            <table
              className={cn(GRID_TABLE, "table-fixed")}
              style={largeurMin(
                130 + 180 + COLONNES_JOUR.length * 120 + (canEdit ? 44 : 0),
                banks.length,
              )}
              aria-label="Prévisions"
            >
              <colgroup>
                <col className="w-[130px]" />
                <col className="w-[180px]" />
                {banks.map((bank) => (
                  <col key={bank.id} />
                ))}
                {COLONNES_JOUR.map((column) => (
                  <col key={column.key} className="w-[120px]" />
                ))}
                {canEdit && <col className="w-[44px]" />}
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
                  {canEdit && (
                    <th scope="col" className={GRID_HEAD}>
                      <span className="sr-only">Supprimer</span>
                    </th>
                  )}
                </tr>
              </thead>
              <tbody>
                {groupes.length === 0 && (
                  <tr>
                    <td
                      colSpan={2 + banks.length + COLONNES_JOUR.length + (canEdit ? 1 : 0)}
                      className="px-3 py-6 text-center text-sm text-simtis-muted"
                    >
                      Aucune prévision à partir du {formatDate(jour)}.
                    </td>
                  </tr>
                )}
                {groupes.flatMap((groupe) =>
                  groupe.lignes.map(({ id }, index) => (
                    <tr key={id}>
                      {index === 0 && (
                        <th
                          scope="rowgroup"
                          rowSpan={groupe.lignes.length}
                          className={cn(GRID_ROW_HEAD, "text-center align-middle")}
                        >
                          <span className="tabular-nums">{formatDate(groupe.jour)}</span>
                          {canEdit && (
                            <button
                              type="button"
                              onClick={() => ajouter(groupe.jour)}
                              disabled={grid.saving || pleine(groupe.jour)}
                              title="Ajouter une ligne à cette date"
                              aria-label={`Ajouter une ligne au ${formatDate(groupe.jour)}`}
                              className={cn(
                                ICON_BUTTON,
                                "mt-1 flex w-full items-center justify-center gap-1 text-xs font-normal hover:bg-simtis-light hover:text-simtis-primary",
                              )}
                            >
                              <Plus className="h-3.5 w-3.5" aria-hidden />
                              ligne
                            </button>
                          )}
                        </th>
                      )}
                      <td className="p-0">
                        {cell(cellKey(id, "libelle"), `${formatDate(groupe.jour)} libellé`, true)}
                      </td>
                      {banks.map((bank) => (
                        <td key={bank.id} className="p-0">
                          {cell(cellKey(id, bank.id), `${formatDate(groupe.jour)} ${bank.code}`)}
                        </td>
                      ))}
                      {COLONNES_JOUR.map((column) => (
                        <td key={column.key} className="p-0">
                          {cell(
                            cellKey(id, column.key),
                            `${formatDate(groupe.jour)} ${column.label}`,
                          )}
                        </td>
                      ))}
                      {canEdit && (
                        <td className="text-center">
                          <button
                            type="button"
                            onClick={() => grid.changeDraft((draft) => supprimerLigne(draft, id))}
                            disabled={grid.saving}
                            title="Supprimer la ligne"
                            aria-label={`Supprimer la ligne ${index + 1} du ${formatDate(groupe.jour)}`}
                            className={cn(
                              ICON_BUTTON,
                              "hover:bg-simtis-danger-bg hover:text-simtis-danger-fg",
                            )}
                          >
                            <Trash2 className="h-4 w-4" aria-hidden />
                          </button>
                        </td>
                      )}
                    </tr>
                  )),
                )}
              </tbody>
            </table>
          </div>
          {canEdit && (
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <label className="flex items-center gap-2 text-sm font-medium text-simtis-text">
                Date de la ligne
                <DateInput
                  id="prevision-nouvelle-date"
                  value={nouvelleDate}
                  min={jour}
                  onChange={(event) => setNouvelleDate(event.target.value)}
                  invalid={nouvelleDate !== "" && !dateValide}
                  className="w-[170px]"
                />
              </label>
              <Button
                variant="secondary"
                icon={Plus}
                onClick={() => ajouter(nouvelleDate)}
                disabled={!dateValide || grid.saving}
              >
                Ajouter une ligne
              </Button>
              {nouvelleDate !== "" && nouvelleDate < jour && (
                <span className="text-sm text-simtis-danger-fg">
                  La date doit être le {formatDate(jour)} ou plus tard.
                </span>
              )}
            </div>
          )}
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
