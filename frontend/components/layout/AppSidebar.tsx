"use client";

import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "@/components/auth/AuthProvider";
import { cn } from "@/lib/cn";
import { NAV_ITEMS } from "@/lib/navigation";
import { canAccess } from "@/lib/permissions";

type AppSidebarProps = {
  /** Mobile : le menu est un tiroir ouvert par le bouton de l'en-tête. */
  mobileOpen: boolean;
  onNavigate: () => void;
  /** Grand écran : réduite aux icônes au choix de l'utilisateur (bouton en bas de la barre). */
  collapsed: boolean;
  onToggleCollapsed: () => void;
};

/**
 * Desktop (lg+) : fixe, 252px, ou réduite aux icônes (72px) si l'utilisateur la réduit. Tablette
 * (md) : réduite aux icônes. Mobile : tiroir. Réduite, le nom de chaque page s'affiche au survol.
 */
export function AppSidebar({
  mobileOpen,
  onNavigate,
  collapsed,
  onToggleCollapsed,
}: AppSidebarProps) {
  const pathname = usePathname();
  const { user } = useAuth();
  // Seules les pages que l'utilisateur peut consulter apparaissent
  const items = NAV_ITEMS.filter((item) => user && canAccess(user.permissions, item.href));

  return (
    <aside
      className={cn(
        "fixed inset-y-0 left-0 z-40 flex w-[var(--simtis-sidebar-width)] flex-col bg-simtis-primary-dark text-white/80 transition-[translate,width] duration-200",
        mobileOpen ? "translate-x-0" : "-translate-x-full",
        "md:w-[var(--simtis-sidebar-collapsed-width)] md:translate-x-0",
        collapsed
          ? "lg:w-[var(--simtis-sidebar-collapsed-width)]"
          : "lg:w-[var(--simtis-sidebar-width)]",
      )}
    >
      <div
        className={cn(
          "flex h-[88px] shrink-0 items-center bg-simtis-card px-5 md:justify-center md:px-2",
          collapsed ? "lg:justify-center lg:px-2" : "lg:justify-start lg:px-5",
        )}
      >
        <Image
          src="/logo-simtis.png"
          alt="SIMTIS — Printing & Weaving"
          width={373}
          height={135}
          priority
          className={cn("h-auto w-[176px] md:w-14", collapsed ? "lg:w-14" : "lg:w-[176px]")}
        />
      </div>

      <nav
        aria-label="Navigation principale"
        className="flex-1 space-y-1 overflow-y-auto px-3 py-4"
      >
        {items.map(({ label, href, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(`${href}/`);
          return (
            <Link
              key={href}
              href={href}
              onClick={onNavigate}
              title={label}
              aria-current={active ? "page" : undefined}
              className={cn(
                "relative flex items-center gap-3 rounded-[10px] px-4 py-2.5 text-[15px] transition-colors duration-200",
                "md:justify-center md:px-0",
                collapsed ? "lg:justify-center lg:px-0" : "lg:justify-start lg:px-4",
                active
                  ? "bg-white/10 text-white before:absolute before:top-2 before:bottom-2 before:left-0 before:w-[3px] before:rounded-full before:bg-simtis-secondary"
                  : "text-white/75 hover:bg-white/5 hover:text-white",
              )}
            >
              <Icon className="h-5 w-5 shrink-0" strokeWidth={1.75} aria-hidden />
              <span className={cn("md:hidden", collapsed ? "lg:hidden" : "lg:inline")}>
                {label}
              </span>
            </Link>
          );
        })}
      </nav>

      <div className={cn("shrink-0 px-3 pb-2 max-lg:hidden", collapsed && "flex justify-center")}>
        <button
          type="button"
          onClick={onToggleCollapsed}
          aria-label={collapsed ? "Agrandir le menu" : "Réduire le menu"}
          title={collapsed ? "Agrandir le menu" : "Réduire le menu"}
          className={cn(
            "flex items-center gap-3 rounded-[10px] py-2.5 text-[15px] text-white/75 transition-colors duration-200 hover:bg-white/5 hover:text-white focus-visible:outline-2 focus-visible:outline-simtis-secondary",
            collapsed ? "justify-center px-3" : "w-full px-4",
          )}
        >
          {collapsed ? (
            <PanelLeftOpen className="h-5 w-5 shrink-0" strokeWidth={1.75} aria-hidden />
          ) : (
            <PanelLeftClose className="h-5 w-5 shrink-0" strokeWidth={1.75} aria-hidden />
          )}
          {!collapsed && <span>Réduire le menu</span>}
        </button>
      </div>

      <div
        className={cn(
          "shrink-0 px-6 py-5 text-xs text-white/60 md:hidden",
          collapsed ? "lg:hidden" : "lg:block",
        )}
      >
        <p className="text-sm font-medium text-white/80">SIMTIS Finance</p>
        <p>v1.0.0</p>
      </div>
    </aside>
  );
}
