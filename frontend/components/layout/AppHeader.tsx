"use client";

import { ChevronDown, LogOut, Menu } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { CompanySelector } from "@/components/company/CompanySelector";
import { AlertBell } from "@/components/layout/AlertBell";
import { cn } from "@/lib/cn";

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
        className="flex items-center gap-3 rounded-full p-1 pr-2 transition-colors duration-200 hover:bg-simtis-surface"
      >
        <span
          aria-hidden
          className="grid h-10 w-10 place-items-center rounded-full bg-simtis-sidebar text-base font-semibold text-white ring-2 ring-simtis-light"
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
          className="absolute right-0 mt-2 w-64 rounded-card border border-simtis-border bg-simtis-card p-2 shadow-simtis-hover"
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
            className="flex w-full items-center gap-2 rounded-[10px] px-3 py-2 text-sm text-simtis-text transition-colors hover:bg-simtis-surface disabled:opacity-60"
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
    <header className="sticky top-0 z-20 flex h-[var(--simtis-header-height)] items-center justify-between gap-4 border-b border-simtis-border/80 bg-simtis-card/85 px-4 backdrop-blur-md sm:px-6 lg:px-8">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <button
          type="button"
          onClick={onMenuClick}
          aria-label="Ouvrir le menu"
          className="rounded-[10px] p-2 text-simtis-text transition-colors hover:bg-simtis-surface md:hidden"
        >
          <Menu className="h-6 w-6" aria-hidden />
        </button>
        {/* Recherche globale masquée tant qu'elle n'est pas construite (21/10/2026) */}
      </div>

      <div className="flex items-center gap-2 sm:gap-3">
        <CompanySelector />
        <AlertBell />
        <UserMenu />
      </div>
    </header>
  );
}
