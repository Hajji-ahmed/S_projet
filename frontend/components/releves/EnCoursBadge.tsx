/** Opération en cours (libellé terminé par « (*) », 20/10/2026) : jamais rapprochée tant que sa
 * définitive n'est pas importée ; remplacée, elle reste dans le relevé pour son solde. */
export function EnCoursBadge({ remplacee = false }: { remplacee?: boolean }) {
  return remplacee ? (
    <span className="mt-0.5 inline-block rounded-full bg-simtis-background px-2 py-0.5 text-xs font-medium text-simtis-muted line-through">
      Remplacée
    </span>
  ) : (
    <span className="mt-0.5 inline-block rounded-full bg-simtis-warning-bg px-2 py-0.5 text-xs font-medium text-simtis-warning-fg">
      En cours
    </span>
  );
}
