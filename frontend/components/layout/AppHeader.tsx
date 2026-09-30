import { Bell, ChevronDown, Menu } from "lucide-react";

import { SearchBar } from "@/components/ui/SearchBar";

// Utilisateur fictif : remplacé par l'utilisateur connecté quand l'authentification existera.
const CURRENT_USER = { name: "Salma", role: "Trésorerie" };
// Nombre d'alertes non lues : 0 tant qu'il n'y a pas de centre de notifications.
const UNREAD_NOTIFICATIONS = 0;

export function AppHeader({ onMenuClick }: { onMenuClick: () => void }) {
  return (
    <header className="sticky top-0 z-20 flex h-[var(--simtis-header-height)] items-center justify-between gap-4 border-b border-simtis-border bg-simtis-card px-4 sm:px-6">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <button
          type="button"
          onClick={onMenuClick}
          aria-label="Ouvrir le menu"
          className="rounded-lg p-2 text-simtis-text transition-colors hover:bg-simtis-light md:hidden"
        >
          <Menu className="h-6 w-6" aria-hidden />
        </button>
        <SearchBar />
      </div>

      <div className="flex items-center gap-2 sm:gap-4">
        <button
          type="button"
          aria-label="Notifications"
          className="relative rounded-lg p-2 text-simtis-text transition-colors hover:bg-simtis-light"
        >
          <Bell className="h-[22px] w-[22px]" aria-hidden />
          {UNREAD_NOTIFICATIONS > 0 && (
            <span className="absolute top-0.5 right-0.5 grid h-[18px] min-w-[18px] place-items-center rounded-full bg-simtis-danger px-1 text-[11px] font-semibold text-white">
              {UNREAD_NOTIFICATIONS}
            </span>
          )}
        </button>

        <button
          type="button"
          className="flex items-center gap-3 rounded-lg p-1 transition-colors hover:bg-simtis-light"
        >
          <span
            aria-hidden
            className="grid h-10 w-10 place-items-center rounded-full bg-simtis-primary text-base font-semibold text-white"
          >
            {CURRENT_USER.name.charAt(0)}
          </span>
          <span className="hidden text-left sm:block">
            <span className="block text-sm leading-tight font-semibold text-simtis-text">
              {CURRENT_USER.name}
            </span>
            <span className="block text-xs text-simtis-muted">{CURRENT_USER.role}</span>
          </span>
          <ChevronDown className="hidden h-4 w-4 text-simtis-muted sm:block" aria-hidden />
        </button>
      </div>
    </header>
  );
}
