/** Ligne en proposition (statut « À vérifier », 28/10/2026) : elle reste « Non rapprochée » dans les
 * volets et le compteur tant que le rapprochement n'est pas validé. */
export function PropositionBadge() {
  return (
    <span
      className="mt-0.5 inline-block shrink-0 rounded-full bg-simtis-info-bg px-2 py-0.5 text-[11px] font-medium text-simtis-info-fg"
      title="Une proposition de rapprochement attend une validation (onglet Propositions)."
    >
      En proposition
    </span>
  );
}
