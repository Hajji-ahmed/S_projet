import {
  BookText,
  Calculator,
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

export type NavItem = { label: string; href: string; icon: LucideIcon };

/**
 * Entrées de la barre latérale, dans l'ordre d'affichage. Ne jamais renommer une route existante.
 * Pas de pages Prévisions ni Devises (décision du 05/10/2026) : leurs tableaux sont sur la page
 * Position bancaire.
 */
export const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Banques", href: "/banques", icon: Landmark },
  { label: "Comptes", href: "/comptes", icon: WalletCards },
  { label: "Relevés", href: "/releves", icon: FileSpreadsheet },
  { label: "Écritures comptables", href: "/ecritures", icon: BookText },
  { label: "Rapprochement", href: "/rapprochement", icon: GitCompare },
  // Frais bancaires à passer dans Sage : leur page depuis le 21/11/2026 (onglet avant)
  { label: "À comptabiliser", href: "/a-comptabiliser", icon: Calculator },
  { label: "Position bancaire", href: "/position-bancaire", icon: TrendingUp },
  { label: "Rapports", href: "/rapports", icon: FileText },
  { label: "Administration", href: "/administration", icon: Settings },
];
