import { Search } from "lucide-react";

/** Barre de recherche de l'en-tête. Non branchée pour l'instant : la recherche arrive avec les modules. */
export function SearchBar() {
  return (
    <label className="relative block w-full max-w-[520px]">
      <span className="sr-only">Rechercher</span>
      <Search
        className="pointer-events-none absolute top-1/2 left-4 h-[18px] w-[18px] -translate-y-1/2 text-simtis-muted"
        aria-hidden
      />
      <input
        type="search"
        placeholder="Rechercher un compte, une transaction, un relevé..."
        className="h-11 w-full rounded-full border border-transparent bg-simtis-surface pr-4 pl-11 text-sm text-simtis-text transition-colors duration-200 placeholder:text-simtis-muted hover:border-simtis-border focus:border-simtis-primary focus:bg-simtis-card focus:ring-4 focus:ring-simtis-primary/10 focus:outline-none"
      />
    </label>
  );
}
