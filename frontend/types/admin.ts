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
