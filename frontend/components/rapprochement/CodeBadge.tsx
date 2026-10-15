/** Code d'un rapprochement validé (« BP-26-000123 », 13/10/2026), ou un tiret. */
export function CodeBadge({ code }: { code: string | null | undefined }) {
  if (!code) return <span className="text-simtis-muted">-</span>;
  return (
    <span className="inline-flex rounded-md bg-simtis-light px-1.5 py-0.5 font-mono text-xs whitespace-nowrap text-simtis-primary-dark">
      {code}
    </span>
  );
}
