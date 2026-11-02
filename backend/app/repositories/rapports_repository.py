"""Rapports (P16.4) : lectures des lignes non rapprochées d'une période."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AccountingEntry, BankTransaction

# Lignes non rapprochées (30/10/2026) : non rapprochée, en proposition (« À vérifier ») ou en écart
STATUTS_NON_RAPPROCHES = ("Non rapprochée", "À vérifier", "Écart")


def operations_non_rapprochees(
    db: Session, account_id: int, date_from: date, date_to: date
) -> list[BankTransaction]:
    """Opérations du compte non rapprochées de la période, la plus récente d'abord ; les opérations
    en cours « (*) » et celles remplacées par leur définitive sont exclues."""
    return list(
        db.scalars(
            select(BankTransaction)
            .where(
                BankTransaction.bank_account_id == account_id,
                BankTransaction.date_operation.between(date_from, date_to),
                BankTransaction.statut.in_(STATUTS_NON_RAPPROCHES),
                BankTransaction.en_cours.is_(False),
                BankTransaction.remplacee_par_id.is_(None),
            )
            .order_by(BankTransaction.date_operation.desc(), BankTransaction.id.desc())
        )
    )


def ecritures_non_rapprochees(
    db: Session, account_id: int, date_from: date, date_to: date
) -> list[AccountingEntry]:
    """Écritures du compte non rapprochées de la période, la plus récente d'abord."""
    return list(
        db.scalars(
            select(AccountingEntry)
            .where(
                AccountingEntry.bank_account_id == account_id,
                AccountingEntry.date_ecriture.between(date_from, date_to),
                AccountingEntry.statut.in_(STATUTS_NON_RAPPROCHES),
            )
            .order_by(AccountingEntry.date_ecriture.desc(), AccountingEntry.id.desc())
        )
    )
