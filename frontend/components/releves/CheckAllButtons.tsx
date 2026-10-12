import { Button } from "@/components/ui/Button";

/** Groupe de lignes cochable d'un clic (erreurs, doublons internes). */
export type GroupeLignes = { label: string; numeros: readonly number[] };

type CheckAllButtonsProps = {
  /** Lignes cochées / lignes cochables. */
  checked: number;
  total: number;
  onCheckAll: () => void;
  onUncheckAll: () => void;
  /** Sélection actuelle et groupes « Cocher · Décocher » (10/10/2026). */
  selection?: ReadonlySet<number>;
  groupes?: GroupeLignes[];
  onGroupe?: (numeros: readonly number[], cocher: boolean) => void;
};

/** « Tout cocher · Tout décocher », puis par groupe, à l'étape Validation (relevés et Sage). */
export function CheckAllButtons({
  checked,
  total,
  onCheckAll,
  onUncheckAll,
  selection,
  groupes = [],
  onGroupe,
}: CheckAllButtonsProps) {
  return (
    <div className="mb-3 space-y-2">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm text-simtis-muted tabular-nums">
          {checked} / {total} ligne{total > 1 ? "s" : ""} cochée{checked > 1 ? "s" : ""}
        </span>
        <Button variant="secondary" onClick={onCheckAll} disabled={checked === total}>
          Tout cocher
        </Button>
        <Button variant="secondary" onClick={onUncheckAll} disabled={checked === 0}>
          Tout décocher
        </Button>
      </div>
      {selection && onGroupe && groupes.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          {groupes.map(({ label, numeros }) => {
            const coches = numeros.filter((numero) => selection.has(numero)).length;
            return (
              <div key={label} className="flex items-center gap-2">
                <span className="text-sm text-simtis-text tabular-nums">
                  {label} ({numeros.length})
                </span>
                <Button
                  variant="ghost"
                  onClick={() => onGroupe(numeros, true)}
                  disabled={numeros.length === 0 || coches === numeros.length}
                >
                  Cocher
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => onGroupe(numeros, false)}
                  disabled={coches === 0}
                >
                  Décocher
                </Button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
