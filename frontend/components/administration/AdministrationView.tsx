"use client";

import { ShieldCheck, SlidersHorizontal, UserRound } from "lucide-react";
import { useState } from "react";

import { ParametresTab } from "@/components/administration/ParametresTab";
import { RolesTab } from "@/components/administration/RolesTab";
import { UsersTab } from "@/components/administration/UsersTab";
import { useAuth } from "@/components/auth/AuthProvider";
import { PageHeader } from "@/components/ui/PageHeader";
import { cn } from "@/lib/cn";
import { PERMISSIONS, hasAnyPermission } from "@/lib/permissions";

type Onglet = "utilisateurs" | "roles" | "parametres";

/** Administration (P16) : un onglet par droit, l'API vérifie chaque action. */
export function AdministrationView() {
  const { user } = useAuth();
  const granted = user?.permissions ?? [];
  const onglets = (
    [
      ["utilisateurs", "Utilisateurs", UserRound, PERMISSIONS.ADMIN_USERS],
      ["roles", "Rôles et permissions", ShieldCheck, PERMISSIONS.ADMIN_ROLES],
      ["parametres", "Paramètres", SlidersHorizontal, PERMISSIONS.ADMIN_SETTINGS],
    ] as const
  ).filter(([, , , permission]) => hasAnyPermission(granted, [permission]));
  const [choisi, setChoisi] = useState<Onglet | null>(null);
  const onglet = choisi ?? onglets[0]?.[0] ?? null;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Administration"
        description="Utilisateurs, rôles, permissions et paramètres de SIMTIS Finance"
      />
      {onglets.length > 1 && (
        <div
          className="flex gap-2 border-b border-simtis-border"
          role="tablist"
          aria-label="Administration"
        >
          {onglets.map(([value, label, Icon]) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={onglet === value}
              onClick={() => setChoisi(value)}
              className={cn(
                "-mb-px flex items-center gap-2 border-b-2 px-3 py-2 text-sm font-medium transition-colors duration-200",
                onglet === value
                  ? "border-simtis-primary text-simtis-primary-dark"
                  : "border-transparent text-simtis-muted hover:text-simtis-primary",
              )}
            >
              <Icon className="h-4 w-4" aria-hidden />
              {label}
            </button>
          ))}
        </div>
      )}
      {onglet === "utilisateurs" && <UsersTab />}
      {onglet === "roles" && <RolesTab />}
      {onglet === "parametres" && <ParametresTab />}
    </div>
  );
}
