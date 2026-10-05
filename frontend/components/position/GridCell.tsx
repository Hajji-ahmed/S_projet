import { CircleAlert, RotateCcw, Save } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";

/**
 * Style des tableaux du classeur (Banques, Devises, Prévisions), aligné sur `DataTable` : cadre
 * arrondi, en-têtes teal clair, texte normal, survol des lignes ; en plus, des traits verticaux
 * fins (grilles de montants et de saisie). Les couleurs viennent des tokens.
 */
/** Cadre du tableau : arrondi, bordure claire ; seul le tableau défile sur mobile. */
export const GRID_FRAME =
  "relative overflow-x-auto rounded-[12px] border border-simtis-border bg-simtis-card";
// border-hidden : le contour extérieur est celui du cadre arrondi, pas celui des cellules
export const GRID_TABLE =
  "w-full border-collapse border-hidden text-[13.5px] text-simtis-text [&_td]:border [&_td]:border-simtis-border [&_th]:border [&_th]:border-simtis-border [&_tbody_tr]:transition-colors [&_tbody_tr:hover]:bg-simtis-light/40";
/** En-tête de colonne, comme `DataTable`. */
export const GRID_HEAD =
  "bg-simtis-light/60 px-3 py-2.5 text-center text-[13px] font-semibold whitespace-nowrap text-simtis-primary-dark";
/** Libellé de ligne (Taux, LIGNE, EUR, date des Prévisions...). */
export const GRID_ROW_HEAD = "px-3 py-2.5 text-left font-medium whitespace-nowrap";
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
      <span className={cn("block min-h-10 px-3 py-2.5 whitespace-nowrap", alignment)}>{value}</span>
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
        "block h-10 w-full min-w-0 bg-transparent px-3 outline-none",
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
