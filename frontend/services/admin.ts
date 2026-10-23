import { apiFetch } from "@/lib/api";
import type {
  AdminPermission,
  AdminRole,
  AdminUser,
  ChangementsPersonne,
  PasswordResult,
  PermissionPersonne,
  RoleInput,
  UserInput,
} from "@/types/admin";

const JSON_HEADERS = { "Content-Type": "application/json" };

export function listUsers() {
  return apiFetch<AdminUser[]>("/admin/users");
}

export function createUser(data: UserInput) {
  return apiFetch<PasswordResult>("/admin/users", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });
}

export function updateUser(id: number, data: UserInput) {
  return apiFetch<AdminUser>(`/admin/users/${id}`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });
}

export function setUserStatus(id: number, actif: boolean) {
  return apiFetch<AdminUser>(`/admin/users/${id}/status`, {
    method: "PATCH",
    headers: JSON_HEADERS,
    body: JSON.stringify({ actif }),
  });
}

export function resetPassword(id: number) {
  return apiFetch<PasswordResult>(`/admin/users/${id}/password`, { method: "POST" });
}

export function listRoles() {
  return apiFetch<AdminRole[]>("/admin/roles");
}

export function listPermissions() {
  return apiFetch<AdminPermission[]>("/admin/permissions");
}

export function createRole(data: RoleInput) {
  return apiFetch<AdminRole>("/admin/roles", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });
}

export function updateRole(id: number, data: RoleInput) {
  return apiFetch<AdminRole>(`/admin/roles/${id}`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });
}

export function deleteRole(id: number) {
  return apiFetch<void>(`/admin/roles/${id}`, { method: "DELETE" });
}

/** Permissions d'une personne : origine et état final (23/10/2026). */
export function getUserPermissions(id: number) {
  return apiFetch<PermissionPersonne[]>(`/admin/users/${id}/permissions`);
}

/** Remplace les ajouts et retraits de permissions de la personne, tout ou rien. */
export function setUserPermissions(id: number, changements: ChangementsPersonne) {
  return apiFetch<PermissionPersonne[]>(`/admin/users/${id}/permissions`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(changements),
  });
}
