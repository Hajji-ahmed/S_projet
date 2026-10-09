import type { ReactNode } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { cn } from "@/lib/cn";

export type Column<T> = {
  key: string;
  header: string;
  /** « right » pour les montants : alignement à droite, chiffres tabulaires. */
  align?: "left" | "right";
  render?: (row: T) => ReactNode;
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
};

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
}: DataTableProps<T>) {
  const cellClass = (column: Column<T>) =>
    cn("px-4 py-3", column.align === "right" && "text-right whitespace-nowrap tabular-nums");

  return (
    <div
      className={cn(
        "overflow-x-auto rounded-[12px] border border-simtis-border bg-simtis-card",
        className,
      )}
    >
      <table className="w-full border-collapse text-[13.5px] text-simtis-text">
        <thead>
          <tr
            className={cn(
              "text-[13px] font-semibold text-simtis-primary-dark",
              // En-tête collant : fond opaque, sinon les lignes défilent à travers
              stickyHeader ? "sticky top-0 z-10 bg-simtis-light" : "bg-simtis-light/60",
            )}
          >
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={cn(
                  "px-4 py-3 whitespace-nowrap",
                  column.align === "right" ? "text-right" : "text-left",
                )}
              >
                {column.header}
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
                    "border-b border-simtis-border/70 transition-colors last:border-b-0",
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
