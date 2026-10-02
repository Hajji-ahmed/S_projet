from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.models import BankAccountBalance, User


def list_for_account(
    db: Session, account_id: int, date_from: date, date_to: date
) -> list[tuple[BankAccountBalance, str | None]]:
    """Soldes d'un compte sur une période, du plus récent au plus ancien, avec le nom de l'auteur."""
    query = (
        select(BankAccountBalance, User.nom)
        .outerjoin(User, User.id == BankAccountBalance.saisi_par_id)
        .where(
            BankAccountBalance.bank_account_id == account_id,
            BankAccountBalance.date_solde >= date_from,
            BankAccountBalance.date_solde <= date_to,
        )
        .order_by(BankAccountBalance.date_solde.desc())
    )
    return [(balance, nom) for balance, nom in db.execute(query)]


def get(db: Session, account_id: int, jour: date) -> BankAccountBalance | None:
    query = select(BankAccountBalance).where(
        BankAccountBalance.bank_account_id == account_id, BankAccountBalance.date_solde == jour
    )
    return db.scalar(query)


def add(db: Session, balance: BankAccountBalance) -> BankAccountBalance:
    db.add(balance)
    db.flush()
    return balance


def latest_by_field(
    db: Session, account_ids: list[int], as_of: date
) -> tuple[dict[int, tuple[date, Decimal]], dict[int, tuple[date, Decimal]]]:
    """Pour chaque compte : dernier solde connu et dernier crédit utilisé connu, jusqu'à `as_of`.

    Deux requêtes `DISTINCT ON` : une ligne par compte, quel que soit l'historique accumulé.
    """
    if not account_ids:
        return {}, {}

    def latest(column) -> dict[int, tuple[date, Decimal]]:
        query = (
            select(BankAccountBalance.bank_account_id, BankAccountBalance.date_solde, column)
            .where(
                BankAccountBalance.bank_account_id.in_(account_ids),
                BankAccountBalance.date_solde <= as_of,
                column.is_not(None),
            )
            .ext(distinct_on(BankAccountBalance.bank_account_id))
            .order_by(BankAccountBalance.bank_account_id, BankAccountBalance.date_solde.desc())
        )
        return {account_id: (jour, value) for account_id, jour, value in db.execute(query)}

    return latest(BankAccountBalance.solde), latest(BankAccountBalance.credit_utilise)
