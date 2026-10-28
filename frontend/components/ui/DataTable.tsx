import type { ReactNode } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { cn } from "@/lib/cn";

export type Column<T> = {
  key: string;
  header: string;
  /** « right » pour les montants : alignement à droite, chiffres tabulaires. */
  align?: "left" | "right";
  render?: (row: T) => ReactNode;
  /** Colonne figée à droite quand le tableau défile (Actions, 21/10/2026). */
  sticky?: boolean;
  /** Filtre placé dans l'en-tête, à côté du titre, comme dans Excel (volets du rapprochement,
   * 28/10/2026). */
  filtre?: ReactNode;
};

type DataTableProps<T> = {
  columns: Column<T>[];
  rows: T[];
  getRowKey: (row: T) => string;
  /** Ligne « Total » en bas, par clé de colonne. */
  footer?: Partial<Record<string, ReactNode>>;
  emptyMessage?: string;
  className?: string;
  /** Clic (ou Entrée / Espace) sur une ligne : la ligne devient sélectionnable. */
  onRowClick?: (row: T) => void;
  /** Ligne sélectionnée : fond `simtis-light`. */
  isRowSelected?: (row: T) => boolean;
  /** Nom accessible d'une ligne cliquable (lu par les lecteurs d'écran). */
  rowLabel?: (row: T) => string;
  /** Ligne mise en retrait (texte grisé), par exemple une ligne décochée d'un aperçu d'import. */
  isRowMuted?: (row: T) => boolean;
  /** Ligne d'en-tête toujours visible quand le tableau défile dans un conteneur de hauteur fixe. */
  stickyHeader?: boolean;
  /** Lignes serrées (volets du rapprochement, 27/10/2026, resserrées le 28/10/2026) : environ 28 px
   * par ligne, texte en 12 px. */
  dense?: boolean;
  /** Le tableau défile dans son cadre et arrive près du bas : charger la suite (28/10/2026). */
  onScrollEnd?: () => void;
};

// Cellule figée à droite : fond opaque, sinon les colonnes défilent à travers
const STICKY_CELL = "sticky right-0 z-[1] border-l border-simtis-border/70 bg-simtis-card";

/**
 * Tableau de base, avec sélection d'une ligne au clic (`onRowClick`, `isRowSelected`). Le tri et la
 * sélection multiple seront ajoutés dans les phases dont les pages en ont besoin. Les tableaux Banques, Devises et
 * Prévisions ont une structure imposée : ils ne passent pas par ce composant générique.
 */
export function DataTable<T extends Record<string, unknown>>({
  columns,
  rows,
  getRowKey,
  footer,
  emptyMessage = "Aucune donnée disponible.",
  className,
  onRowClick,
  isRowSelected,
  rowLabel,
  isRowMuted,
  stickyHeader = false,
  dense = false,
  onScrollEnd,
}: DataTableProps<T>) {
  const espacement = dense ? "px-2 py-1" : "px-4 py-3";
  const cellClass = (column: Column<T>) =>
    cn(
      espacement,
      column.align === "right" && "text-right whitespace-nowrap tabular-nums",
      column.sticky && STICKY_CELL,
    );

  return (
    <div
      className={cn(
        "overflow-x-auto rounded-card border border-simtis-border bg-simtis-card",
        className,
      )}
      onScroll={
        onScrollEnd
          ? (event) => {
              const cadre = event.currentTarget;
              if (cadre.scrollHeight - cadre.scrollTop - cadre.clientHeight < 300) onScrollEnd();
            }
          : undefined
      }
    >
      <table
        className={cn(
          "w-full border-collapse text-simtis-text",
          dense ? "text-xs" : "text-[13.5px]",
        )}
      >
        <thead>
          <tr
            className={cn(
              "font-semibold text-simtis-primary-dark",
              dense ? "text-xs" : "text-[13px]",
              // En-tête collant : fond opaque, sinon les lignes défilent à travers
              stickyHeader ? "sticky top-0 z-10 bg-simtis-light" : "bg-simtis-light/60",
            )}
          >
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={cn(
                  espacement,
                  "whitespace-nowrap",
                  column.align === "right" ? "text-right" : "text-left",
                  column.sticky && cn(STICKY_CELL, "bg-simtis-light"),
                )}
              >
                {column.filtre ? (
                  <span
                    className={cn(
                      "inline-flex items-center gap-1",
                      column.align === "right" && "flex-row-reverse",
                    )}
                  >
                    {column.header}
                    {column.filtre}
                  </span>
                ) : (
                  column.header
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length}>
                <EmptyState message={emptyMessage} />
              </td>
            </tr>
          ) : (
            rows.map((row) => {
              const selected = isRowSelected?.(row) ?? false;
              return (
                <tr
                  key={getRowKey(row)}
                  aria-selected={onRowClick ? selected : undefined}
                  aria-label={onRowClick && rowLabel ? rowLabel(row) : undefined}
                  tabIndex={onRowClick ? 0 : undefined}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  onKeyDown={
                    onRowClick
                      ? (event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            onRowClick(row);
                          }
                        }
                      : undefined
                  }
                  className={cn(
                    "border-b border-simtis-border/70 transition-colors duration-150 last:border-b-0",
                    selected ? "bg-simtis-light" : "bg-simtis-card hover:bg-simtis-light/40",
                    isRowMuted?.(row) && "text-simtis-muted",
                    onRowClick &&
                      "cursor-pointer focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-simtis-secondary",
                  )}
                >
                  {columns.map((column) => (
                    <td key={column.key} className={cellClass(column)}>
                      {column.render ? column.render(row) : (row[column.key] as ReactNode)}
                    </td>
                  ))}
                </tr>
              );
            })
          )}
        </tbody>
        {footer && rows.length > 0 && (
          <tfoot>
            <tr className="border-t border-simtis-border bg-simtis-background font-semibold">
              {columns.map((column) => (
                <td key={column.key} className={cellClass(column)}>
                  {footer[column.key]}
                </td>
              ))}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  );
}
