import { cn } from "@/lib/cn";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded bg-simtis-light/60", className)} />;
}

/** Squelette de tableau ou de liste, à afficher pendant le chargement des données. */
export function LoadingState({ rows = 4 }: { rows?: number }) {
  return (
    <div role="status" aria-busy="true" className="space-y-3">
      <span className="sr-only">Chargement...</span>
      <Skeleton className="h-9 w-full" />
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} className="h-6 w-full" />
      ))}
    </div>
  );
}
