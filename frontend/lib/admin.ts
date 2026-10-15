/** Administration (P16.1) : règles d'affichage pures. Les vraies règles sont vérifiées par l'API. */
import type { AdminPermission, AdminRole } from "@/types/admin";

/** Permissions groupées par module, dans l'ordre reçu de l'API. */
export function parModule(permissions: AdminPermission[]): [string, AdminPermission[]][] {
  const groupes = new Map<string, AdminPermission[]>();
  for (const permission of permissions) {
    const groupe = groupes.get(permission.module) ?? [];
    groupe.push(permission);
    groupes.set(permission.module, groupe);
  }
  return [...groupes.entries()];
}

/** Brouillon de la matrice : rôle → ensemble de codes de permission. */
export type Matrice = Record<number, string[]>;

export function matriceDe(roles: AdminRole[]): Matrice {
  return Object.fromEntries(roles.map((role) => [role.id, [...role.permissions].sort()]));
}

/** Coche ou décoche une case, sans modifier le brouillon reçu. */
export function basculer(matrice: Matrice, roleId: number, code: string): Matrice {
  const actuelles = matrice[roleId] ?? [];
  const suivantes = actuelles.includes(code)
    ? actuelles.filter((c) => c !== code)
    : [...actuelles, code].sort();
  return { ...matrice, [roleId]: suivantes };
}

/** Rôles dont le brouillon diffère de l'état enregistré. */
export function rolesModifies(roles: AdminRole[], matrice: Matrice): AdminRole[] {
  return roles.filter((role) => {
    const avant = [...role.permissions].sort().join(",");
    return (matrice[role.id] ?? []).join(",") !== avant;
  });
}

/** Permissions que le rôle Administrateur ne peut pas perdre (même règle que l'API). */
export const PERMISSIONS_ADMIN = ["admin.users", "admin.roles"] as const;

export function caseVerrouillee(role: AdminRole, code: string): boolean {
  return role.code === "ADMIN" && (PERMISSIONS_ADMIN as readonly string[]).includes(code);
}
