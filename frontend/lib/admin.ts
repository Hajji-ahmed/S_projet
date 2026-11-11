/** Administration (P16.1) : règles d'affichage pures. Les vraies règles sont vérifiées par l'API. */
import type {
  AdminPermission,
  AdminRole,
  ChangementsPersonne,
  PermissionPersonne,
} from "@/types/admin";

/** Permissions groupées par module, dans l'ordre reçu de l'API. */
export function parModule<T extends AdminPermission>(permissions: T[]): [string, T[]][] {
  const groupes = new Map<string, T[]>();
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

/**
 * Ajouts et retraits à envoyer pour une personne (23/10/2026) : une case cochée que ses rôles ne
 * donnent pas est un ajout ; une case décochée que ses rôles donnent est un retrait. Le reste suit
 * les rôles et n'est pas envoyé (l'API recalcule de toute façon).
 */
export function changementsPersonne(
  permissions: PermissionPersonne[],
  cochees: ReadonlySet<string>,
): ChangementsPersonne {
  const ajouts: string[] = [];
  const retraits: string[] = [];
  for (const permission of permissions) {
    const parRole = permission.par_roles.length > 0;
    if (cochees.has(permission.code) && !parRole) ajouts.push(permission.code);
    if (!cochees.has(permission.code) && parRole) retraits.push(permission.code);
  }
  return { ajouts: ajouts.sort(), retraits: retraits.sort() };
}

/**
 * Initiales d'un avatar (11/11/2026) : première lettre du premier et du dernier mot
 * (« Mustapha El Alaoui » → « MA »), deux premières lettres d'un seul mot, « ? » sans nom.
 */
export function initiales(nom: string): string {
  const mots = nom.trim().split(/\s+/).filter(Boolean);
  if (mots.length === 0) return "?";
  if (mots.length === 1) return mots[0].slice(0, 2).toUpperCase();
  return (mots[0].charAt(0) + mots[mots.length - 1].charAt(0)).toUpperCase();
}

// Couleurs d'avatar, toutes tirées des tokens (fond clair, texte foncé)
const COULEURS_AVATAR = [
  "bg-simtis-light text-simtis-primary",
  "bg-simtis-info-bg text-simtis-info-fg",
  "bg-simtis-violet-bg text-simtis-violet-fg",
  "bg-simtis-success-bg text-simtis-success-fg",
  "bg-simtis-warning-bg text-simtis-warning-fg",
] as const;

/** Couleur stable d'un utilisateur, d'après son id : la même à chaque affichage. */
export function couleurAvatar(id: number): string {
  return COULEURS_AVATAR[Math.abs(id) % COULEURS_AVATAR.length];
}
