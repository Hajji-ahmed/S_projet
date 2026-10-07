import {
  AlertTriangle,
  BookText,
  FileSpreadsheet,
  FileText,
  GitCompare,
  Landmark,
  LayoutDashboard,
  Settings,
  TrendingUp,
  WalletCards,
  type LucideIcon,
} from "lucide-react";

import { ECARTS_ACTIFS } from "@/lib/features";

export type NavItem = { label: string; href: string; icon: LucideIcon };

/**
 * Entrées de la barre latérale, dans l'ordre d'affichage. Ne jamais renommer une route existante.
 * Pas de pages Prévisions ni Devises (décision du 05/10/2026) : leurs tableaux sont sur la page
 * Position bancaire.
 */
const ALL_NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Banques", href: "/banques", icon: Landmark },
  { label: "Comptes", href: "/comptes", icon: WalletCards },
  { label: "Relevés", href: "/releves", icon: FileSpreadsheet },
  { label: "Écritures comptables", href: "/ecritures", icon: BookText },
  { label: "Rapprochement", href: "/rapprochement", icon: GitCompare },
  { label: "Écarts", href: "/ecarts", icon: AlertTriangle },
  { label: "Position bancaire", href: "/position-bancaire", icon: TrendingUp },
  { label: "Rapports", href: "/rapports", icon: FileText },
  { label: "Administration", href: "/administration", icon: Settings },
];

/** Entrées visibles : sans « Écarts » tant que la fonction est mise de côté (`ECARTS_ACTIFS`). */
export function navItems(ecartsActifs: boolean): NavItem[] {
  return ALL_NAV_ITEMS.filter((item) => ecartsActifs || item.href !== "/ecarts");
}

export const NAV_ITEMS: NavItem[] = navItems(ECARTS_ACTIFS);
