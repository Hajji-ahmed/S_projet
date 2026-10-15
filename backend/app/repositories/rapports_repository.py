"""Rapports (P16.4) : lectures de l'état de rapprochement d'une période."""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BankTransaction


def statuts_par_compte(
    db: Session, account_ids: list[int], date_from: date, date_to: date
) -> dict[int, dict[str, tuple[int, Decimal, Decimal]]]:
    """{compte: {statut: (nombre, débits, crédits)}} des opérations de la période."""
    if not account_ids:
        return {}
    rows = db.execute(
        select(
            BankTransaction.bank_account_id,
            BankTransaction.statut,
            func.count(),
            func.coalesce(func.sum(BankTransaction.debit), 0),
            func.coalesce(func.sum(BankTransaction.credit), 0),
        )
        .where(
            BankTransaction.bank_account_id.in_(account_ids),
            BankTransaction.date_operation.between(date_from, date_to),
        )
        .group_by(BankTransaction.bank_account_id, BankTransaction.statut)
    )
    resultat: dict[int, dict[str, tuple[int, Decimal, Decimal]]] = {}
    for compte, statut, nombre, debit, credit in rows:
        resultat.setdefault(compte, {})[statut] = (nombre, Decimal(debit), Decimal(credit))
    return resultat


def non_rapprochees(
    db: Session, account_ids: list[int], date_from: date, date_to: date
) -> list[BankTransaction]:
    """Opérations de la période qui ne sont pas « Rapprochée », par compte puis par date."""
    if not account_ids:
        return []
    return list(
        db.scalars(
            select(BankTransaction)
            .where(
                BankTransaction.bank_account_id.in_(account_ids),
                BankTransaction.date_operation.between(date_from, date_to),
                BankTransaction.statut != "Rapprochée",
            )
            .order_by(
                BankTransaction.bank_account_id,
                BankTransaction.date_operation,
                BankTransaction.id,
            )
        )
    )
