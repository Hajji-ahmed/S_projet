"use client";

import { Bell, ChevronDown, LogOut, Menu } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { CompanySelector } from "@/components/company/CompanySelector";
import { SearchBar } from "@/components/ui/SearchBar";
import { cn } from "@/lib/cn";

// Nombre d'alertes non lues : 0 tant qu'il n'y a pas de centre de notifications.
const UNREAD_NOTIFICATIONS = 0;

function UserMenu() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    window.addEventListener("mousedown", closeOnOutsideClick);
    return () => {
      window.removeEventListener("keydown", closeOnEscape);
      window.removeEventListener("mousedown", closeOnOutsideClick);
    };
  }, [open]);

  if (!user) return null;
  const role = user.roles.join(", ") || "Aucun rôle";

  // La session devient anonyme : RequireAuth renvoie alors vers la page de connexion
  async function handleLogout() {
    setLeaving(true);
    await logout();
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((isOpen) => !isOpen)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex items-center gap-3 rounded-lg p-1 transition-colors hover:bg-simtis-light"
      >
        <span
          aria-hidden
          className="grid h-10 w-10 place-items-center rounded-full bg-simtis-primary text-base font-semibold text-white"
        >
          {user.nom.charAt(0).toUpperCase()}
        </span>
        <span className="hidden max-w-[180px] text-left sm:block">
          <span className="block truncate text-sm leading-tight font-semibold text-simtis-text">
            {user.nom}
          </span>
          <span className="block truncate text-xs text-simtis-muted">{role}</span>
        </span>
        <ChevronDown
          className={cn(
            "hidden h-4 w-4 text-simtis-muted transition-transform duration-200 sm:block",
            open && "rotate-180",
          )}
          aria-hidden
        />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 mt-2 w-64 rounded-[12px] border border-simtis-border bg-simtis-card p-2 shadow-simtis"
        >
          <div className="px-3 py-2">
            <p className="truncate text-sm font-semibold text-simtis-text">{user.nom}</p>
            <p className="truncate text-xs text-simtis-muted">{user.email}</p>
            <p className="mt-1 truncate text-xs text-simtis-primary">{role}</p>
          </div>
          <div className="my-1 border-t border-simtis-border" />
          <button
            type="button"
            role="menuitem"
            onClick={handleLogout}
            disabled={leaving}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-simtis-text transition-colors hover:bg-simtis-light disabled:opacity-60"
          >
            <LogOut className="h-4 w-4 text-simtis-muted" aria-hidden />
            {leaving ? "Déconnexion..." : "Se déconnecter"}
          </button>
        </div>
      )}
    </div>
  );
}

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
        <CompanySelector />
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
        <UserMenu />
      </div>
    </header>
  );
}
