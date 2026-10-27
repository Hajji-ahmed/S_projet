"""Lectures de la reprise d'un état de rapprochement (27/10/2026)."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AccountingEntry, BankTransaction


def operations_jusqu_au(db: Session, bank_account_id: int, jusqu_au: date) -> list[BankTransaction]:
    """Toutes les opérations du compte datées au plus tard de `jusqu_au`."""
    return list(
        db.scalars(
            select(BankTransaction)
            .where(
                BankTransaction.bank_account_id == bank_account_id,
                BankTransaction.date_operation <= jusqu_au,
            )
            .order_by(BankTransaction.date_operation, BankTransaction.id)
        )
    )


def ecritures_jusqu_au(db: Session, bank_account_id: int, jusqu_au: date) -> list[AccountingEntry]:
    """Toutes les écritures du compte datées au plus tard de `jusqu_au`."""
    return list(
        db.scalars(
            select(AccountingEntry)
            .where(
                AccountingEntry.bank_account_id == bank_account_id,
                AccountingEntry.date_ecriture <= jusqu_au,
            )
            .order_by(AccountingEntry.date_ecriture, AccountingEntry.id)
        )
    )
