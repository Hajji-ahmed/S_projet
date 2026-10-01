from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Bank, BankAccount


def list_banks(db: Session) -> list[Bank]:
    """Toutes les banques, actives ou non, dans l'ordre des colonnes des tableaux."""
    return list(db.scalars(select(Bank).order_by(Bank.ordre_affichage, Bank.code)))


def get(db: Session, bank_id: int) -> Bank | None:
    return db.get(Bank, bank_id)


def get_by_code(db: Session, code: str) -> Bank | None:
    return db.scalar(select(Bank).where(Bank.code == code))


def active_account_counts(db: Session, company_id: int | None = None) -> dict[int, int]:
    """Nombre de comptes actifs par banque : d'une société, ou de toutes si `company_id` est None."""
    query = (
        select(BankAccount.bank_id, func.count())
        .where(BankAccount.actif.is_(True))
        .group_by(BankAccount.bank_id)
    )
    if company_id is not None:
        query = query.where(BankAccount.company_id == company_id)
    return {bank_id: count for bank_id, count in db.execute(query)}


def max_display_order(db: Session) -> int | None:
    return db.scalar(select(func.max(Bank.ordre_affichage)))


def add(db: Session, bank: Bank) -> Bank:
    db.add(bank)
    db.flush()
    return bank
