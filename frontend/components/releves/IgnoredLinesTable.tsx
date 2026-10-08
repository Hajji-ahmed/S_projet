"use client";

import { useState } from "react";

import { DataTable, type Column } from "@/components/ui/DataTable";
import { Pagination } from "@/components/ui/Pagination";
import { cellulesText, pageOf } from "@/lib/importLines";
import type { LigneIgnoree } from "@/types/statement";

/**
 * Lignes du fichier qui ne seront pas importées et la raison (titre, total, SOLDE INITIAL, autre
 * journal, contrepartie…). Lecture seule : elles ne bloquent rien et ne se corrigent pas ici.
 */
export function IgnoredLinesTable({ lignes }: { lignes: LigneIgnoree[] }) {
  const [page, setPage] = useState(1);
  const shown = pageOf(lignes, page);
  const columns: Column<LigneIgnoree>[] = [
    {
      key: "numero",
      header: "Ligne",
      align: "right",
      render: (row) => row.numero,
    },
    {
      key: "raison",
      header: "Raison",
      render: (row) => <span className="block min-w-[220px]">{row.raison}</span>,
    },
    {
      key: "cellules",
      header: "Contenu de la ligne",
      render: (row) => (
        <span className="block min-w-[260px] text-simtis-muted">{cellulesText(row.cellules)}</span>
      ),
    },
  ];
  return (
    <>
      <DataTable
        columns={columns}
        rows={shown.rows}
        getRowKey={(row) => String(row.numero)}
        emptyMessage="Aucune ligne ignorée dans ce fichier."
      />
      {lignes.length > 0 && (
        <Pagination
          label="Pages des lignes ignorées"
          page={shown.page}
          pages={shown.pages}
          total={lignes.length}
          noun="ligne ignorée"
          onPage={setPage}
        />
      )}
    </>
  );
}
