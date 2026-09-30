"use client";

import { useEffect, useState, type ReactNode } from "react";

import { AppHeader } from "@/components/layout/AppHeader";
import { AppSidebar } from "@/components/layout/AppSidebar";

export function AppShell({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);

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
      <AppSidebar mobileOpen={mobileOpen} onNavigate={() => setMobileOpen(false)} />
      {mobileOpen && (
        <button
          type="button"
          aria-label="Fermer le menu"
          onClick={() => setMobileOpen(false)}
          className="fixed inset-0 z-30 bg-simtis-text/30 md:hidden"
        />
      )}
      <div className="md:pl-[var(--simtis-sidebar-collapsed-width)] lg:pl-[var(--simtis-sidebar-width)]">
        <AppHeader onMenuClick={() => setMobileOpen(true)} />
        <main className="space-y-6 p-4 sm:p-6 lg:p-8">{children}</main>
      </div>
    </div>
  );
}
