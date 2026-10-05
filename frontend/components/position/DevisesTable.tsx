"use client";

import { Coins } from "lucide-react";
import { useEffect, useState } from "react";

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
import { formatAmount } from "@/lib/format";
import { currencyCell } from "@/lib/position";
import {
  COLONNES_DEVISES,
  LIGNES_DEVISES,
  cellKey,
  devisesToDraft,
  draftToDevisesInput,
} from "@/lib/saisies";
import { getDevisesSoldes } from "@/services/position";
import { getDevises, saveDevises } from "@/services/saisies";
import type { Bank } from "@/types/bank";
import type { DevisesSoldes } from "@/types/position";
import type { Devises, DevisesInput } from "@/types/saisie";

// EUR et USD viennent des comptes en devise : seule la ligne Exp DH convertible se saisit encore.
// Les anciennes valeurs EUR / USD saisies restent en base et sont renvoyées telles quelles.
const LIGNES_SAISIES = LIGNES_DEVISES.filter((ligne) => ligne === "Exp DH convertible");

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

const NUMBER = "px-3 py-2.5 text-right tabular-nums whitespace-nowrap";

/**
 * Tableau Devises du classeur : lignes EUR, USD et Exp DH convertible, cellules de banques grisées,
 * puis TOTAL et DEPASSEMENT. Décision du 05/10/2026 : EUR et USD montrent les soldes des comptes en
 * devise (API, jamais convertis, DEPASSEMENT vide) ; Exp DH convertible reste saisi à la main.
 * Rien n'est affiché pour une société sans compte en devise ni DH convertible (Tefil).
 */
export function DevisesTable({ companyId, jour, banks, canEdit }: DevisesTableProps) {
  const { toast } = useToast();
  const grid = useSaisieGrid(companyId, jour, API);
  const [soldes, setSoldes] = useState<DevisesSoldes | null>(null);
  const [soldesState, setSoldesState] = useState<"loading" | "error" | "ready">("loading");
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getDevisesSoldes(companyId, jour).then(
      (result) => {
        if (cancelled) return;
        setSoldes(result);
        setSoldesState("ready");
      },
      () => {
        if (!cancelled) setSoldesState("error");
      },
    );
    return () => {
      cancelled = true;
    };
  }, [companyId, jour, retryKey]);

  // Société sans compte en devise ni DH convertible : pas de tableau Devises
  if (soldesState === "ready" && soldes && !soldes.affiche) return null;

  const loading = grid.loadState === "loading" || soldesState === "loading";
  const failed = grid.loadState === "error" || soldesState === "error";
  function retry() {
    if (grid.loadState === "error") grid.retry();
    if (soldesState === "error") {
      setSoldesState("loading");
      setRetryKey((key) => key + 1);
    }
  }

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
      {loading && !failed && <LoadingState rows={3} />}
      {failed && <ErrorState message="Impossible de charger le tableau Devises." onRetry={retry} />}
      {!loading && !failed && soldes && (
        <>
          <div className={GRID_FRAME}>
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
                {soldes.lignes.map((ligne) => (
                  <tr key={ligne.devise}>
                    <th scope="row" className={GRID_ROW_HEAD}>
                      {ligne.devise}
                    </th>
                    {banks.map((bank) => {
                      const cellule = ligne.cellules.find((c) => c.bank_id === bank.id);
                      const { text, note } = currencyCell(
                        cellule ?? { valeur: null, date_solde: null, reprise: false },
                        ligne.devise,
                      );
                      return (
                        <td
                          key={bank.id}
                          className={cn(NUMBER, GRID_GREY, note && "text-simtis-muted")}
                          title={note ?? undefined}
                        >
                          {text}
                          {note && <span className="sr-only"> ({note})</span>}
                        </td>
                      );
                    })}
                    <td className={NUMBER}>{formatAmount(ligne.total, ligne.devise)}</td>
                    {/* Pas de DEPASSEMENT en devise (pas de LIGNE en EUR / USD) */}
                    <td />
                  </tr>
                ))}
                {LIGNES_SAISIES.map((ligne) => (
                  <tr key={ligne}>
                    <th scope="row" className={GRID_ROW_HEAD}>
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
