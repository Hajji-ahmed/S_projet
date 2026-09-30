import {
  AlertTriangle,
  BookText,
  ChartLine,
  CircleDollarSign,
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

/** Entrées de la barre latérale, dans l'ordre d'affichage. Ne jamais renommer une route existante. */
export const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Banques", href: "/banques", icon: Landmark },
  { label: "Comptes", href: "/comptes", icon: WalletCards },
  { label: "Relevés", href: "/releves", icon: FileSpreadsheet },
  { label: "Écritures comptables", href: "/ecritures", icon: BookText },
  { label: "Rapprochement", href: "/rapprochement", icon: GitCompare },
  { label: "Écarts", href: "/ecarts", icon: AlertTriangle },
  { label: "Position bancaire", href: "/position-bancaire", icon: TrendingUp },
  { label: "Prévisions", href: "/previsions", icon: ChartLine },
  { label: "Devises", href: "/devises", icon: CircleDollarSign },
  { label: "Rapports", href: "/rapports", icon: FileText },
  { label: "Administration", href: "/administration", icon: Settings },
];
