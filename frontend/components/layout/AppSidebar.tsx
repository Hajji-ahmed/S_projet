"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/cn";
import { NAV_ITEMS } from "@/lib/navigation";

type AppSidebarProps = {
  /** Mobile : le menu est un tiroir ouvert par le bouton de l'en-tête. */
  mobileOpen: boolean;
  onNavigate: () => void;
};

/**
 * Desktop (lg+) : fixe, 252px. Tablette (md) : réduite aux icônes. Mobile : tiroir.
 * Les libellés sont visibles sur mobile (tiroir) et sur desktop, masqués sur tablette.
 */
export function AppSidebar({ mobileOpen, onNavigate }: AppSidebarProps) {
  const pathname = usePathname();

  return (
    <aside
      className={cn(
        "fixed inset-y-0 left-0 z-40 flex w-[var(--simtis-sidebar-width)] flex-col bg-simtis-primary-dark text-white/80 transition-[translate,width] duration-200",
        mobileOpen ? "translate-x-0" : "-translate-x-full",
        "md:w-[var(--simtis-sidebar-collapsed-width)] md:translate-x-0 lg:w-[var(--simtis-sidebar-width)]",
      )}
    >
      <div className="flex h-[88px] shrink-0 items-center bg-simtis-card px-5 md:justify-center md:px-2 lg:justify-start lg:px-5">
        <Image
          src="/logo-simtis.png"
          alt="SIMTIS — Printing & Weaving"
          width={373}
          height={135}
          priority
          className="h-auto w-[176px] md:w-14 lg:w-[176px]"
        />
      </div>

      <nav
        aria-label="Navigation principale"
        className="flex-1 space-y-1 overflow-y-auto px-3 py-4"
      >
        {NAV_ITEMS.map(({ label, href, icon: Icon }) => {
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
                "md:justify-center md:px-0 lg:justify-start lg:px-4",
                active
                  ? "bg-white/10 text-white before:absolute before:top-2 before:bottom-2 before:left-0 before:w-[3px] before:rounded-full before:bg-simtis-secondary"
                  : "text-white/75 hover:bg-white/5 hover:text-white",
              )}
            >
              <Icon className="h-5 w-5 shrink-0" strokeWidth={1.75} aria-hidden />
              <span className="md:hidden lg:inline">{label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="shrink-0 px-6 py-5 text-xs text-white/60 md:hidden lg:block">
        <p className="text-sm font-medium text-white/80">SIMTIS Finance</p>
        <p>v1.0.0</p>
      </div>
    </aside>
  );
}
