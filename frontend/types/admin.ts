/** Administration (P16.1) : utilisateurs, rôles, permissions. */

export type RoleRef = { id: number; code: string; nom: string };

export type AdminUser = {
  id: number;
  nom: string;
  email: string;
  actif: boolean;
  roles: RoleRef[];
  dernier_login: string | null;
  /** Verrouillé après trop d'échecs de connexion (la réinitialisation le débloque). */
  verrouille: boolean;
  created_at: string;
  /** Permissions ajoutées / retirées pour la personne, en plus de ses rôles (23/10/2026). */
  nb_ajouts: number;
  nb_retraits: number;
};

export type UserInput = { nom: string; email: string; role_ids: number[] };

/** Mot de passe provisoire : affiché une seule fois, jamais relu. */
export type PasswordResult = { user: AdminUser; mot_de_passe: string };

export type AdminRole = {
  id: number;
  code: string;
  nom: string;
  description: string | null;
  /** Rôle créé par les seeds : code figé, jamais supprimé. */
  systeme: boolean;
  permissions: string[];
  nb_utilisateurs: number;
};

export type RoleInput = { nom: string; description: string | null; permissions: string[] };

export type AdminPermission = { code: string; description: string; module: string };

/** Une permission vue pour une personne (23/10/2026) : origine et état final. */
export type PermissionPersonne = AdminPermission & {
  /** Rôles de la personne qui la donnent. */
  par_roles: string[];
  /** null : comme ses rôles ; true : ajoutée ; false : retirée. */
  personnalisation: boolean | null;
  effective: boolean;
  /** Case verrouillée : un administrateur garde l'administration des utilisateurs et des rôles. */
  verrouillee: boolean;
};

export type ChangementsPersonne = { ajouts: string[]; retraits: string[] };
