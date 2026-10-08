import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/Button";

/** « N opérations · Page 1 sur 3 » avec Précédent / Suivant (seulement s'il y a plusieurs pages). */
export function Pagination({
  label,
  page,
  pages,
  total,
  noun,
  onPage,
}: {
  label: string;
  page: number;
  pages: number;
  total: number;
  noun: string;
  onPage: (page: number) => void;
}) {
  return (
    <nav
      aria-label={label}
      className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm"
    >
      <p className="text-simtis-muted">
        {total} {noun}
        {total > 1 ? "s" : ""}
        {pages > 1 && ` · Page ${page} sur ${pages}`}
      </p>
      {pages > 1 && (
        <div className="flex gap-2">
          <Button
            variant="secondary"
            icon={ChevronLeft}
            disabled={page <= 1}
            onClick={() => onPage(page - 1)}
          >
            Précédent
          </Button>
          <Button
            variant="secondary"
            icon={ChevronRight}
            disabled={page >= pages}
            onClick={() => onPage(page + 1)}
          >
            Suivant
          </Button>
        </div>
      )}
    </nav>
  );
}
