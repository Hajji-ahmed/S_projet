"""Données de référence, nécessaires au fonctionnement de l'application (production comprise)."""

from collections import Counter
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.permissions import PERMISSION_DESCRIPTIONS, PermissionCode
from app.models import (
    Bank,
    Company,
    Currency,
    ForecastCategory,
    Permission,
    PointageType,
    ReconciliationRule,
    Role,
)
from app.seeds.common import get_or_create
from app.seeds.pointages import CATEGORIES_POINTAGE
from app.services.normalization_service import pointage_code

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

# Les 74 catégories du métier (décision du 08/10/2026) ; liste ouverte, l'administrateur pourra en
# ajouter (P16). Code interne tiré du libellé.
POINTAGE_TYPES = [(pointage_code(libelle), libelle) for libelle in CATEGORIES_POINTAGE]

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

# Grille du rapprochement 1→1, non encore validée par Mustapha : (code, libellé, critère, points ou
# valeur du seuil, tolérance, actif). Décision du 07/10/2026 : pour le moment, seuls le montant, la
# date et le libellé comptent ; la référence et le tiers sont désactivés (migration 0014 pour une base
# existante). Elle se modifie en base ; un nouveau seed ne l'écrase jamais.
# Codes lus par `reconciliation_service.grille()` ; valeurs par défaut : `reconciliation_scoring.Grille`.
RECONCILIATION_RULES = [
    ("REFERENCE", "Référence / n° chèque / n° pièce identique", "reference", "40", None, False),
    ("MONTANT", "Montant exact, sens opposé", "montant", "50", None, True),
    ("DATE", "Date dans la tolérance (jours), dégressif", "date", "30", "3", True),
    ("LIBELLE", "Libellé similaire", "libelle", "20", None, True),
    ("TIERS", "Tiers retrouvé dans le libellé bancaire", "tiers", "5", None, False),
    ("FENETRE", "Fenêtre de comparaison des dates (jours)", "fenetre", "0", "10", True),
    ("SEUIL_PROPOSITION", "Score minimal d'une proposition", "seuil", "50", None, True),
    ("SEUIL_FORT", "Score d'une forte correspondance", "seuil", "90", None, True),
    (
        "ECART_AMBIGUITE",
        "Écart de points sous lequel deux candidats sont ambigus",
        "seuil",
        "10",
        None,
        True,
    ),
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

    for code, libelle, critere, poids, tolerance, actif in RECONCILIATION_RULES:
        get_or_create(
            session,
            ReconciliationRule,
            {"code": code},
            {
                "libelle": libelle,
                "critere": critere,
                "poids": Decimal(poids),
                "tolerance": None if tolerance is None else Decimal(tolerance),
                "actif": actif,
            },
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
