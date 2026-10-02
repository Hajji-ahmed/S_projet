"""Calculs de position (CDC §5.2). Fonctions pures, en `Decimal`, sans accès à la base.

    Crédit disponible   = Crédit autorisé (LIGNE) − Crédit utilisé
    Position disponible = Solde bancaire + Crédit disponible

Une valeur inconnue (jamais saisie) reste inconnue (`None`) : elle n'est jamais remplacée par zéro.
Réutilisé par la position bancaire (P8).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol
from zoneinfo import ZoneInfo

# Les dates de solde sont celles du Maroc, pas celles du serveur (UTC)
BUSINESS_TZ = ZoneInfo("Africa/Casablanca")


def business_today() -> date:
    return datetime.now(BUSINESS_TZ).date()


class BalanceLike(Protocol):
    date_solde: date
    solde: Decimal | None
    credit_utilise: Decimal | None


@dataclass(frozen=True)
class LatestValues:
    solde: Decimal | None
    credit_utilise: Decimal | None
    date_maj: date | None


@dataclass(frozen=True)
class AccountFigures:
    solde: Decimal | None
    credit_utilise: Decimal | None
    credit_disponible: Decimal | None
    position_disponible: Decimal | None
    date_maj: date | None


def credit_disponible(credit_autorise: Decimal, credit_utilise: Decimal | None) -> Decimal | None:
    """Peut être négatif : le crédit utilisé dépasse alors la LIGNE (dépassement)."""
    if credit_utilise is None:
        return None
    return credit_autorise - credit_utilise


def position_disponible(solde: Decimal | None, credit_dispo: Decimal | None) -> Decimal | None:
    if solde is None or credit_dispo is None:
        return None
    return solde + credit_dispo


def latest_values(balances: Iterable[BalanceLike], as_of: date | None = None) -> LatestValues:
    """Dernière valeur connue de chaque champ, jusqu'à `as_of` inclus.

    Le solde et le crédit utilisé peuvent venir de dates différentes ; la date de mise à jour est la
    dernière date où l'un des deux a été renseigné.
    """
    solde: tuple[date, Decimal] | None = None
    utilise: tuple[date, Decimal] | None = None
    for balance in balances:
        if as_of is not None and balance.date_solde > as_of:
            continue
        if balance.solde is not None and (solde is None or balance.date_solde > solde[0]):
            solde = (balance.date_solde, balance.solde)
        if balance.credit_utilise is not None and (
            utilise is None or balance.date_solde > utilise[0]
        ):
            utilise = (balance.date_solde, balance.credit_utilise)

    dates = [value[0] for value in (solde, utilise) if value is not None]
    return LatestValues(
        solde=solde[1] if solde else None,
        credit_utilise=utilise[1] if utilise else None,
        date_maj=max(dates) if dates else None,
    )


def account_figures(credit_autorise: Decimal, latest: LatestValues) -> AccountFigures:
    dispo = credit_disponible(credit_autorise, latest.credit_utilise)
    return AccountFigures(
        solde=latest.solde,
        credit_utilise=latest.credit_utilise,
        credit_disponible=dispo,
        position_disponible=position_disponible(latest.solde, dispo),
        date_maj=latest.date_maj,
    )
