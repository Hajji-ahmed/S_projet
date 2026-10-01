"""Codes de permission : source unique, utilisée par les routes, les seeds et les tests.

Le frontend en garde une copie (`frontend/lib/permissions.ts`) ; un test vérifie que les deux listes
sont identiques. Pour ajouter une permission : l'ajouter ici ET dans le frontend, puis un seed la crée.
"""

from enum import StrEnum


class PermissionCode(StrEnum):
    BANKS_MANAGE = "banks.manage"
    STATEMENTS_IMPORT = "statements.import"
    POSITION_VIEW = "position.view"
    ACCOUNTING_IMPORT = "accounting.import"
    RECONCILIATION_VIEW = "reconciliation.view"
    RECONCILIATION_VALIDATE = "reconciliation.validate"
    DISCREPANCIES_MANAGE = "discrepancies.manage"
    FORECASTS_MANAGE = "forecasts.manage"
    DASHBOARD_VIEW = "dashboard.view"
    ADMIN_USERS = "admin.users"
    ADMIN_ROLES = "admin.roles"
    AUDIT_VIEW = "audit.view"


PERMISSION_DESCRIPTIONS: dict[PermissionCode, str] = {
    PermissionCode.BANKS_MANAGE: "Gérer les banques et les comptes bancaires",
    PermissionCode.STATEMENTS_IMPORT: "Importer des relevés bancaires",
    PermissionCode.POSITION_VIEW: "Consulter la position bancaire",
    PermissionCode.ACCOUNTING_IMPORT: "Importer les écritures comptables",
    PermissionCode.RECONCILIATION_VIEW: "Consulter le rapprochement",
    PermissionCode.RECONCILIATION_VALIDATE: "Valider ou rejeter un rapprochement",
    PermissionCode.DISCREPANCIES_MANAGE: "Traiter et clôturer les écarts",
    PermissionCode.FORECASTS_MANAGE: "Gérer les prévisions de trésorerie",
    PermissionCode.DASHBOARD_VIEW: "Consulter le dashboard",
    PermissionCode.ADMIN_USERS: "Administrer les utilisateurs",
    PermissionCode.ADMIN_ROLES: "Administrer les rôles et les permissions",
    PermissionCode.AUDIT_VIEW: "Consulter l'historique des actions",
}
