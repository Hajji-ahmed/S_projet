import { Button } from "@/components/ui/Button";
import { formatAmount } from "@/lib/format";

/** Pied d'un volet chargé au défilement (28/10/2026) : « 300 / 8 487 opérations ». Le bouton sert
 * quand le volet ne défile pas dans son cadre (petit écran, première page trop courte). */
export function PiedDefilement({
  chargees,
  total,
  nom,
  suite,
  reste,
  onChargerPlus,
}: {
  chargees: number;
  total: number;
  nom: string;
  suite: boolean;
  reste: boolean;
  onChargerPlus: () => void;
}) {
  return (
    <div className="mt-2 flex min-h-7 items-center justify-between gap-2 text-xs text-simtis-muted">
      <p className="tabular-nums">
        {formatAmount(chargees)} / {formatAmount(total)} {nom}
        {total > 1 ? "s" : ""}
      </p>
      {suite ? (
        <span role="status">Chargement…</span>
      ) : (
        reste && (
          <Button variant="ghost" className="h-7 px-2 text-xs" onClick={onChargerPlus}>
            Charger la suite
          </Button>
        )
      )}
    </div>
  );
}
