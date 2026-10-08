"use client";

import { useEffect, useState, useSyncExternalStore, type ReactNode } from "react";

import { AppHeader } from "@/components/layout/AppHeader";
import { AppSidebar } from "@/components/layout/AppSidebar";
import { cn } from "@/lib/cn";
import { isCollapsed, setCollapsed, subscribe } from "@/lib/sidebar";

export function AppShell({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  // Grand écran : barre réduite aux icônes au choix de l'utilisateur (agrandie côté serveur)
  const collapsed = useSyncExternalStore(subscribe, isCollapsed, () => false);

  useEffect(() => {
    if (!mobileOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [mobileOpen]);

  return (
    <div className="min-h-screen bg-simtis-background">
      <AppSidebar
        mobileOpen={mobileOpen}
        onNavigate={() => setMobileOpen(false)}
        collapsed={collapsed}
        onToggleCollapsed={() => setCollapsed(!collapsed)}
      />
      {mobileOpen && (
        <button
          type="button"
          aria-label="Fermer le menu"
          onClick={() => setMobileOpen(false)}
          className="fixed inset-0 z-30 bg-simtis-text/30 md:hidden"
        />
      )}
      <div
        className={cn(
          "transition-[padding] duration-200 md:pl-[var(--simtis-sidebar-collapsed-width)]",
          collapsed
            ? "lg:pl-[var(--simtis-sidebar-collapsed-width)]"
            : "lg:pl-[var(--simtis-sidebar-width)]",
        )}
      >
        <AppHeader onMenuClick={() => setMobileOpen(true)} />
        <main className="space-y-6 p-4 sm:p-6 lg:p-8">{children}</main>
      </div>
    </div>
  );
}
