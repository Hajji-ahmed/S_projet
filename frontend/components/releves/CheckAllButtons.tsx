import { Button } from "@/components/ui/Button";

type CheckAllButtonsProps = {
  /** Lignes cochées / lignes cochables. */
  checked: number;
  total: number;
  onCheckAll: () => void;
  onUncheckAll: () => void;
};

/** « Tout cocher · Tout décocher » de l'étape Validation (relevés et Sage). */
export function CheckAllButtons({
  checked,
  total,
  onCheckAll,
  onUncheckAll,
}: CheckAllButtonsProps) {
  return (
    <div className="mb-3 flex flex-wrap items-center gap-3">
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
  );
}
