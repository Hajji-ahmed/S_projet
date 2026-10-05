/**
 * Codes de permission. Copie de `backend/app/core/permissions.py` (source de vérité) : un test vérifie
 * que les deux listes sont identiques.
 *
 * Masquer un menu ne protège rien : c'est l'API qui refuse (401 / 403). L'interface évite seulement
 * de montrer ce que l'utilisateur ne pourra pas utiliser.
 */
export const PERMISSIONS = {
  BANKS_MANAGE: "banks.manage",
  STATEMENTS_IMPORT: "statements.import",
  POSITION_VIEW: "position.view",
  ACCOUNTING_IMPORT: "accounting.import",
  RECONCILIATION_VIEW: "reconciliation.view",
  RECONCILIATION_VALIDATE: "reconciliation.validate",
  DISCREPANCIES_MANAGE: "discrepancies.manage",
  FORECASTS_MANAGE: "forecasts.manage",
  DASHBOARD_VIEW: "dashboard.view",
  ADMIN_USERS: "admin.users",
  ADMIN_ROLES: "admin.roles",
  AUDIT_VIEW: "audit.view",
} as const;

export type PermissionCode = (typeof PERMISSIONS)[keyof typeof PERMISSIONS];

const P = PERMISSIONS;

/**
 * Permissions qui rendent une page visible : il suffit d'en avoir UNE. Consulter n'est pas agir :
 * les boutons d'action exigeront leur propre permission (« manage », « import », « validate »).
 */
export const ROUTE_PERMISSIONS: Record<string, readonly PermissionCode[]> = {
  "/dashboard": [P.DASHBOARD_VIEW],
  "/rapports": [P.DASHBOARD_VIEW],
  "/banques": [P.POSITION_VIEW],
  "/comptes": [P.POSITION_VIEW],
  "/position-bancaire": [P.POSITION_VIEW],
  "/releves": [P.STATEMENTS_IMPORT, P.RECONCILIATION_VIEW],
  "/ecritures": [P.ACCOUNTING_IMPORT, P.RECONCILIATION_VIEW],
  "/rapprochement": [P.RECONCILIATION_VIEW],
  "/ecarts": [P.RECONCILIATION_VIEW],
  "/administration": [P.ADMIN_USERS, P.ADMIN_ROLES],
  "/historique": [P.AUDIT_VIEW],
};

export function hasAnyPermission(
  granted: readonly string[],
  required: readonly PermissionCode[],
): boolean {
  return required.length === 0 || required.some((code) => granted.includes(code));
}

/** Permissions exigées par une page (route exacte ou sous-route). Aucune exigence : tout connecté. */
export function requiredPermissionsFor(pathname: string): readonly PermissionCode[] {
  const route = Object.keys(ROUTE_PERMISSIONS).find(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
  return route ? ROUTE_PERMISSIONS[route] : [];
}

export function canAccess(granted: readonly string[], pathname: string): boolean {
  return hasAnyPermission(granted, requiredPermissionsFor(pathname));
}
