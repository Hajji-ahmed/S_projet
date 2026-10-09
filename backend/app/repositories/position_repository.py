"""Lectures des tableaux Banques (P8.1) et Devises (soldes EUR / USD)."""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.models import Bank, BankAccount, BankAccountBalance, BankTransaction


def active_banks(db: Session) -> list[Bank]:
    """Banques actives, dans l'ordre des colonnes des tableaux."""
    query = select(Bank).where(Bank.actif.is_(True)).order_by(Bank.ordre_affichage, Bank.code)
    return list(db.scalars(query))


def current_mad_accounts(db: Session, company_id: int) -> list[BankAccount]:
    """Comptes courants MAD actifs de la société : au plus un par banque (index unique partiel)."""
    query = select(BankAccount).where(
        BankAccount.company_id == company_id,
        BankAccount.type_compte == "Courant",
        BankAccount.devise == "MAD",
        BankAccount.actif.is_(True),
    )
    return list(db.scalars(query))


def currency_accounts(db: Session, company_id: int, devises: Sequence[str]) -> list[BankAccount]:
    """Comptes courants actifs de la société dans ces devises (EUR, USD) : un par banque et devise."""
    query = select(BankAccount).where(
        BankAccount.company_id == company_id,
        BankAccount.type_compte == "Courant",
        BankAccount.devise.in_(devises),
        BankAccount.actif.is_(True),
    )
    return list(db.scalars(query))


def has_currency_table(db: Session, company_id: int, devises: Sequence[str]) -> bool:
    """La société a-t-elle un compte actif en devise (EUR, USD) ou DH convertible ?"""
    query = select(BankAccount.id).where(
        BankAccount.company_id == company_id,
        BankAccount.actif.is_(True),
        or_(BankAccount.devise.in_(devises), BankAccount.type_compte == "DH convertible"),
    )
    return db.scalar(query.limit(1)) is not None


def soldes_until(
    db: Session, account_ids: list[int], date_fin: date
) -> list[tuple[int, date, Decimal]]:
    """(compte, date, solde) des soldes renseignés jusqu'à `date_fin` incluse.

    Une ligne qui ne porte qu'un crédit utilisé (solde vide) n'est pas un solde.
    """
    if not account_ids:
        return []
    query = select(
        BankAccountBalance.bank_account_id, BankAccountBalance.date_solde, BankAccountBalance.solde
    ).where(
        BankAccountBalance.bank_account_id.in_(account_ids),
        BankAccountBalance.date_solde <= date_fin,
        BankAccountBalance.solde.is_not(None),
    )
    return [(row[0], row[1], row[2]) for row in db.execute(query)]


def last_operation_soldes(
    db: Session, account_ids: list[int], date_fin: date
) -> list[tuple[int, date, Decimal]]:
    """(compte, date d'opération, solde) de la dernière opération de chaque jour qui a un solde,
    jusqu'à `date_fin` incluse. « Dernière » = ordre chronologique du relevé continu (date,
    relevé, rang dans le relevé), jamais l'ordre des lignes du fichier."""
    if not account_ids:
        return []
    query = (
        select(
            BankTransaction.bank_account_id,
            BankTransaction.date_operation,
            BankTransaction.solde,
        )
        .where(
            BankTransaction.bank_account_id.in_(account_ids),
            BankTransaction.date_operation <= date_fin,
            BankTransaction.solde.is_not(None),
        )
        # Une ligne par compte et par jour : la dernière dans l'ordre chronologique
        .ext(distinct_on(BankTransaction.bank_account_id, BankTransaction.date_operation))
        .order_by(
            BankTransaction.bank_account_id,
            BankTransaction.date_operation,
            BankTransaction.statement_id.desc(),
            BankTransaction.ordre.desc(),
            BankTransaction.id.desc(),
        )
    )
    return [(row[0], row[1], row[2]) for row in db.execute(query)]


def comptes_alimentes_par_releve(db: Session, account_ids: list[int]) -> set[int]:
    """Comptes qui ont au moins une opération importée portant un solde : leur solde vient du
    relevé, jamais d'une saisie (décision du 08/10/2026)."""
    if not account_ids:
        return set()
    query = (
        select(BankTransaction.bank_account_id)
        .where(
            BankTransaction.bank_account_id.in_(account_ids),
            BankTransaction.solde.is_not(None),
        )
        .distinct()
    )
    return set(db.scalars(query))


def dernier_solde_releve(
    db: Session, account_ids: list[int], date_fin: date
) -> dict[int, tuple[date, Decimal]]:
    """Par compte : (jour, solde) de la dernière opération importée jusqu'à `date_fin`, dans l'ordre
    chronologique du relevé continu : le solde de clôture."""
    if not account_ids:
        return {}
    query = (
        select(
            BankTransaction.bank_account_id,
            BankTransaction.date_operation,
            BankTransaction.solde,
        )
        .where(
            BankTransaction.bank_account_id.in_(account_ids),
            BankTransaction.date_operation <= date_fin,
            BankTransaction.solde.is_not(None),
        )
        .ext(distinct_on(BankTransaction.bank_account_id))
        .order_by(
            BankTransaction.bank_account_id,
            BankTransaction.date_operation.desc(),
            BankTransaction.statement_id.desc(),
            BankTransaction.ordre.desc(),
            BankTransaction.id.desc(),
        )
    )
    return {row[0]: (row[1], row[2]) for row in db.execute(query)}
