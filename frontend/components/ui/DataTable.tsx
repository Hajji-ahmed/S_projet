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
};

/**
 * Tableau de base. Le tri, la pagination et la sélection multiple seront ajoutés
 * dans les phases dont les pages en ont besoin. Les tableaux Banques, Devises et
 * Prévisions ont une structure imposée : ils ne passent pas par ce composant générique.
 */
export function DataTable<T extends Record<string, unknown>>({
  columns,
  rows,
  getRowKey,
  footer,
  emptyMessage = "Aucune donnée disponible.",
  className,
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
          <tr className="bg-simtis-light/60 text-[13px] font-semibold text-simtis-primary-dark">
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
            rows.map((row) => (
              <tr
                key={getRowKey(row)}
                className="border-b border-simtis-border/70 bg-simtis-card transition-colors last:border-b-0 hover:bg-simtis-light/40"
              >
                {columns.map((column) => (
                  <td key={column.key} className={cellClass(column)}>
                    {column.render ? column.render(row) : (row[column.key] as ReactNode)}
                  </td>
                ))}
              </tr>
            ))
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
