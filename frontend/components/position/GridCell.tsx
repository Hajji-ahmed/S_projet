import { CircleAlert, RotateCcw, Save } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";

/**
 * Cellules des tableaux du classeur (Devises, Prévisions) : bordures fines, police 13px semi-grasse,
 * en-têtes centrés. Les couleurs viennent des tokens.
 */
export const GRID_TABLE =
  "w-full border-collapse text-[13px] font-semibold text-simtis-text [&_td]:border [&_td]:border-simtis-muted [&_th]:border [&_th]:border-simtis-muted";
export const GRID_HEAD = "px-2 py-1.5 text-center font-semibold whitespace-nowrap";
/** Fond gris clair du classeur (cellules de banques des Devises, en-têtes Encaissement...). */
export const GRID_GREY = "bg-simtis-neutral-bg";

type GridCellProps = {
  /** Nom lu par les lecteurs d'écran, ex. « EUR AWB ». */
  label: string;
  value: string;
  onChange: (value: string) => void;
  readOnly: boolean;
  invalid?: boolean;
  align?: "left" | "right";
  maxLength?: number;
};

/** Contenu d'une cellule : un champ sans bordure qui la remplit, ou le texte seul en lecture. */
export function GridCell({
  label,
  value,
  onChange,
  readOnly,
  invalid,
  align = "right",
  maxLength,
}: GridCellProps): ReactNode {
  const alignment = align === "right" ? "text-right tabular-nums" : "text-left";
  if (readOnly) {
    return (
      <span className={cn("block min-h-8 px-2 py-1.5 whitespace-nowrap", alignment)}>{value}</span>
    );
  }
  return (
    <input
      type="text"
      inputMode={align === "right" ? "decimal" : undefined}
      aria-label={label}
      aria-invalid={invalid || undefined}
      value={value}
      maxLength={maxLength}
      onChange={(event) => onChange(event.target.value)}
      className={cn(
        "block h-8 w-full min-w-0 bg-transparent px-2 outline-none",
        "focus:bg-simtis-card focus:ring-2 focus:ring-simtis-primary focus:ring-inset",
        invalid && "bg-simtis-danger-bg text-simtis-danger-fg ring-1 ring-simtis-danger ring-inset",
        alignment,
      )}
    />
  );
}

type GridFooterProps = {
  /** Nom du tableau, pour les boutons (« Enregistrer le tableau Devises »). */
  name: string;
  dirty: boolean;
  saving: boolean;
  invalidCount: number;
  error: string | null;
  onReset: () => void;
  onSave: () => void;
};

/** Message d'erreur et boutons sous une grille modifiable. */
export function GridFooter({
  name,
  dirty,
  saving,
  invalidCount,
  error,
  onReset,
  onSave,
}: GridFooterProps) {
  const message =
    error ??
    (invalidCount > 0
      ? `${invalidCount} cellule${invalidCount > 1 ? "s" : ""} à corriger : un montant, 2 décimales au plus (ex. 1 200 000 ou -15 000,50).`
      : null);
  return (
    <div className="mt-4 flex flex-wrap items-center justify-end gap-3">
      {message && (
        <p
          role="alert"
          className="mr-auto flex items-start gap-2 rounded-lg bg-simtis-danger-bg px-3 py-2 text-sm text-simtis-danger-fg"
        >
          <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          <span>{message}</span>
        </p>
      )}
      <Button
        variant="secondary"
        icon={RotateCcw}
        onClick={onReset}
        disabled={!dirty || saving}
        aria-label={`Annuler les modifications du tableau ${name}`}
      >
        Annuler
      </Button>
      <Button
        icon={Save}
        onClick={onSave}
        disabled={!dirty || saving}
        aria-label={`Enregistrer le tableau ${name}`}
      >
        {saving ? "Enregistrement..." : "Enregistrer"}
      </Button>
    </div>
  );
}
