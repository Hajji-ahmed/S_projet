"""Soldes du jour et crédit utilisé, saisis à la main (décision §3.3), et chiffres des comptes.

Règles :
- une ligne par compte et par jour ; la saisir à nouveau la corrige (l'audit garde l'avant) ;
- pas de saisie dans le futur, ni avant le 01/01/2000 (année mal saisie), ni sur un compte inactif ;
- la source passe à « Saisie » (un relevé importé en P7 portera la source « Relevé »).
"""

from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models import BankAccount, BankAccountBalance
from app.repositories import balance_repository
from app.services import account_service, audit_service, position_service
from app.services.errors import ConflictError
from app.services.position_service import AccountFigures, LatestValues

CENT = Decimal("0.01")
DEFAULT_HISTORY_DAYS = 30
FIELDS = ("solde", "credit_utilise", "commentaire")


def _amount(value: Decimal | None) -> Decimal | None:
    return None if value is None else value.quantize(CENT)


def figures_for_accounts(
    db: Session, accounts: Iterable[BankAccount], as_of: date | None = None
) -> dict[int, AccountFigures]:
    """Chiffres de chaque compte à la date `as_of` (aujourd'hui au Maroc par défaut)."""
    accounts = list(accounts)
    as_of = as_of or position_service.business_today()
    soldes, utilises = balance_repository.latest_by_field(db, [a.id for a in accounts], as_of)

    figures = {}
    for account in accounts:
        solde = soldes.get(account.id)
        utilise = utilises.get(account.id)
        dates = [value[0] for value in (solde, utilise) if value is not None]
        latest = LatestValues(
            solde=solde[1] if solde else None,
            credit_utilise=utilise[1] if utilise else None,
            date_maj=max(dates) if dates else None,
        )
        figures[account.id] = position_service.account_figures(account.credit_autorise, latest)
    return figures


def list_balances(
    db: Session, account_id: int, date_from: date | None = None, date_to: date | None = None
) -> list[tuple[BankAccountBalance, str | None]]:
    account_service.get_account(db, account_id)  # 404 si le compte n'existe pas
    date_to = date_to or position_service.business_today()
    date_from = date_from or date_to - timedelta(days=DEFAULT_HISTORY_DAYS - 1)
    if date_from > date_to:
        raise ConflictError("La date de début doit précéder la date de fin.")
    return balance_repository.list_for_account(db, account_id, date_from, date_to)


def _snapshot(balance: BankAccountBalance, fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: getattr(balance, field) for field in fields}


def save_balance(
    db: Session,
    account_id: int,
    jour: date,
    *,
    solde: Decimal | None,
    credit_utilise: Decimal | None,
    commentaire: str | None,
    acteur_id: int,
    ip: str | None = None,
    today: date | None = None,
) -> BankAccountBalance:
    """Crée ou corrige la ligne du jour. Seuls les champs réellement changés sont tracés."""
    account = account_service.get_account(db, account_id)
    if jour > (today or position_service.business_today()):
        raise ConflictError("Impossible de saisir un solde pour une date future.")
    if jour < position_service.PREMIERE_DATE_SOLDE:
        raise ConflictError("Impossible de saisir un solde avant le 01/01/2000 : vérifiez l'année.")
    if not account.actif:
        raise ConflictError(
            f"Le compte {account.bank.code} {account.devise} est inactif : réactivez-le d'abord."
        )

    new_values = {
        "solde": _amount(solde),
        "credit_utilise": _amount(credit_utilise),
        "commentaire": commentaire.strip() if commentaire and commentaire.strip() else None,
    }
    balance = balance_repository.get(db, account.id, jour)

    if balance is None:
        balance = balance_repository.add(
            db,
            BankAccountBalance(
                bank_account_id=account.id,
                date_solde=jour,
                source="Saisie",
                saisi_par_id=acteur_id,
                **new_values,
            ),
        )
        audit_service.log(
            db,
            user_id=acteur_id,
            action="saisie_solde",
            entite="bank_account_balance",
            entite_id=balance.id,
            apres={"bank_account_id": account.id, "date_solde": jour, **new_values},
            ip=ip,
        )
        db.commit()
        return balance

    changed = tuple(field for field in FIELDS if getattr(balance, field) != new_values[field])
    if not changed:
        return balance
    avant = _snapshot(balance, changed)
    for field in changed:
        setattr(balance, field, new_values[field])
    balance.source = "Saisie"
    balance.saisi_par_id = acteur_id
    audit_service.log(
        db,
        user_id=acteur_id,
        action="correction_solde",
        entite="bank_account_balance",
        entite_id=balance.id,
        avant={"date_solde": jour, **avant},
        apres={"date_solde": jour, **_snapshot(balance, changed)},
        ip=ip,
    )
    db.commit()
    return balance
