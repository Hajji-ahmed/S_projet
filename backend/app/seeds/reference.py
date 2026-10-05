"""Données de référence, nécessaires au fonctionnement de l'application (production comprise)."""

from collections import Counter

from sqlalchemy.orm import Session

from app.core.permissions import PERMISSION_DESCRIPTIONS, PermissionCode
from app.models import (
    Bank,
    Company,
    Currency,
    ForecastCategory,
    Permission,
    PointageType,
    Role,
)
from app.seeds.common import get_or_create

# (code, nom). Le nom de la 2e société est provisoire : il se modifie en base, sans toucher au code.
COMPANIES = [
    ("SIMTIS", "Simtis"),
    # Nom confirmé le 05/10/2026 (affichée « Société X » avant) ; le code ne change jamais
    ("SOCX", "Tefil"),
]

# (code, nom, logo, ordre d'affichage). Les tableaux affichent les banques par code, dans cet ordre.
BANKS = [
    ("AWB", "Attijariwafa", "/banques/attijariwafa.png", 1),
    ("BMCE", "BMCE", "/banques/bmce.png", 2),
    ("BP", "BP", "/banques/bp.png", 3),
    ("CIH", "CIH", "/banques/cih.png", 4),
    ("BMCI", "BMCI", "/banques/bmci.png", 5),
]

CURRENCIES = [
    ("MAD", "Dirham marocain"),
    ("EUR", "Euro"),
    ("USD", "Dollar américain"),
]

# Liste ouverte : l'administrateur peut en ajouter (P16)
POINTAGE_TYPES = [
    ("ENCAISSEMENT", "Encaissement"),
    ("DECAISSEMENT", "Décaissement"),
    ("FRAIS_BANCAIRES", "Frais bancaires"),
]

# (code, libellé, sens par défaut). Le sens n'est renseigné que lorsqu'il est certain : Escompte,
# Refinancement, Chèques et Autre restent à trancher avec le métier. Chaque prévision porte son propre sens.
FORECAST_CATEGORIES = [
    ("ENCAISSEMENT", "Encaissement", "Entrée"),
    ("ESCOMPTE", "Escompte", None),
    ("DOUANE", "Douane", "Sortie"),
    ("PAIE", "Paie", "Sortie"),
    ("REFINANCEMENT", "Refinancement", None),
    ("CHEQUES", "Chèques", None),
    ("AUTRE", "Autre", None),
]

# Source unique : app/core/permissions.py
PERMISSIONS = {code.value: description for code, description in PERMISSION_DESCRIPTIONS.items()}

P = PermissionCode
_CONSULTATION = (P.POSITION_VIEW, P.RECONCILIATION_VIEW, P.DASHBOARD_VIEW)

# Matrice de la phase P5, non encore validée par le métier. Elle n'est appliquée qu'à la CRÉATION d'un
# rôle : une modification faite ensuite par l'administrateur n'est jamais écrasée par un nouveau seed.
ROLES: dict[str, tuple[str, tuple[PermissionCode, ...]]] = {
    "ADMIN": ("Administrateur", tuple(PermissionCode)),
    "TRESORERIE": (
        "Trésorerie",
        _CONSULTATION + (P.BANKS_MANAGE, P.STATEMENTS_IMPORT, P.FORECASTS_MANAGE),
    ),
    "COMPTABLE": (
        "Comptable",
        _CONSULTATION + (P.ACCOUNTING_IMPORT, P.RECONCILIATION_VALIDATE, P.DISCREPANCIES_MANAGE),
    ),
    "RESPONSABLE": (
        "Responsable",
        _CONSULTATION + (P.RECONCILIATION_VALIDATE, P.DISCREPANCIES_MANAGE, P.AUDIT_VIEW),
    ),
    "DIRECTION": ("Direction / Consultation", _CONSULTATION),
}


def seed_reference(session: Session) -> Counter[str]:
    """Crée les données de référence manquantes. Retourne le nombre de lignes créées par table.

    Ne valide pas la transaction : c'est à l'appelant de faire `commit()`.
    """
    created: Counter[str] = Counter()

    for code, nom in COMPANIES:
        get_or_create(session, Company, {"code": code}, {"nom": nom}, created)

    for code, nom, logo, ordre in BANKS:
        get_or_create(
            session,
            Bank,
            {"code": code},
            {"nom": nom, "logo": logo, "ordre_affichage": ordre},
            created,
        )

    for code, libelle in CURRENCIES:
        get_or_create(session, Currency, {"code": code}, {"libelle": libelle}, created)

    for code, libelle in POINTAGE_TYPES:
        get_or_create(session, PointageType, {"code": code}, {"libelle": libelle}, created)

    for code, libelle, sens in FORECAST_CATEGORIES:
        get_or_create(
            session,
            ForecastCategory,
            {"code": code},
            {"libelle": libelle, "sens_par_defaut": sens},
            created,
        )

    permissions = {}
    for code, description in PERMISSIONS.items():
        permissions[code], _ = get_or_create(
            session, Permission, {"code": code}, {"description": description}, created
        )

    for code, (nom, permission_codes) in ROLES.items():
        role, is_new = get_or_create(
            session, Role, {"code": code}, {"nom": nom, "systeme": True}, created
        )
        if is_new:
            role.permissions = [permissions[permission] for permission in permission_codes]
            session.flush()

    return created
