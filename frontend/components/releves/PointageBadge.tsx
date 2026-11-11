import { cn } from "@/lib/cn";

/**
 * Pointage d'une opération en pastille légère (11/11/2026) : remplit la colonne sans le poids d'une
 * liste déroulante. Grise quand aucun pointage n'est choisi.
 */
const PASTILLE = "rounded-full text-xs font-medium whitespace-nowrap";
const PLEINE = "bg-simtis-light text-simtis-primary-dark";
const VIDE = "bg-simtis-surface text-simtis-muted";

/** Pointage en lecture seule. `libelle` null : pas encore choisi. */
export function PointageBadge({ libelle }: { libelle: string | null }) {
  return (
    <span className={cn("inline-flex px-2.5 py-0.5 leading-5", PASTILLE, libelle ? PLEINE : VIDE)}>
      {libelle ?? "À choisir"}
    </span>
  );
}

/** Classes du `Select` de pointage modifiable, habillé comme la pastille (même liste, même saisie). */
export function pointageSelectClasses(vide: boolean): string {
  return cn(
    "h-8 min-w-[150px] border-transparent px-3 hover:border-simtis-chart-4",
    PASTILLE,
    vide ? VIDE : PLEINE,
  );
}
