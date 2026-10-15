"""Lectures du dashboard (P15, 14/10/2026) : sommes et comptages sur la période."""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AccountingEntry, BankTransaction
from app.repositories import reconciliation_repository
from app.repositories.import_repository import ORDRE_CHRONOLOGIQUE

STATUTS_A_RAPPROCHER = ("Non rapprochée", "À vérifier")


def mouvements(
    db: Session, account_ids: list[int], date_from: date, date_to: date
) -> tuple[Decimal, Decimal]:
    """(encaissements, décaissements) : sommes des crédits et des débits du relevé."""
    if not account_ids:
        return Decimal("0.00"), Decimal("0.00")
    row = db.execute(
        select(
            func.coalesce(func.sum(BankTransaction.credit), 0),
            func.coalesce(func.sum(BankTransaction.debit), 0),
        ).where(
            BankTransaction.bank_account_id.in_(account_ids),
            BankTransaction.date_operation.between(date_from, date_to),
        )
    ).one()
    return Decimal(row[0]), Decimal(row[1])


def flux_par_jour(
    db: Session, account_ids: list[int], date_from: date, date_to: date
) -> dict[date, tuple[Decimal, Decimal]]:
    """{jour: (encaissements, décaissements)} des jours de la période qui ont un mouvement."""
    if not account_ids:
        return {}
    rows = db.execute(
        select(
            BankTransaction.date_operation,
            func.coalesce(func.sum(BankTransaction.credit), 0),
            func.coalesce(func.sum(BankTransaction.debit), 0),
        )
        .where(
            BankTransaction.bank_account_id.in_(account_ids),
            BankTransaction.date_operation.between(date_from, date_to),
        )
        .group_by(BankTransaction.date_operation)
    )
    return {row[0]: (Decimal(row[1]), Decimal(row[2])) for row in rows}


def statuts(db: Session, account_ids: list[int], date_from: date, date_to: date) -> dict[str, int]:
    """Nombre d'opérations de la période par statut de rapprochement."""
    if not account_ids:
        return {}
    rows = db.execute(
        select(BankTransaction.statut, func.count())
        .where(
            BankTransaction.bank_account_id.in_(account_ids),
            BankTransaction.date_operation.between(date_from, date_to),
        )
        .group_by(BankTransaction.statut)
    )
    return {row[0]: row[1] for row in rows}


def frais_debites(
    db: Session, account_ids: list[int], date_from: date, date_to: date
) -> list[tuple[str, Decimal]]:
    """(libellé, montant positif) des frais bancaires débités sur la période, quel que soit leur
    statut (règle de « À comptabiliser » : pointage ou libellé)."""
    if not account_ids:
        return []
    rows = db.execute(
        select(BankTransaction.libelle, BankTransaction.debit).where(
            BankTransaction.bank_account_id.in_(account_ids),
            BankTransaction.date_operation.between(date_from, date_to),
            BankTransaction.montant < 0,
            reconciliation_repository.frais_bancaire(),
        )
    )
    return [(row[0], Decimal(row[1])) for row in rows]


def frais_a_comptabiliser(
    db: Session, account_ids: list[int], date_from: date, date_to: date
) -> int:
    """Frais bancaires encore « Non rapprochée » de la période (compteur « À comptabiliser »)."""
    if not account_ids:
        return 0
    return (
        db.scalar(
            select(func.count()).where(
                BankTransaction.bank_account_id.in_(account_ids),
                BankTransaction.date_operation.between(date_from, date_to),
                BankTransaction.statut == "Non rapprochée",
                reconciliation_repository.frais_bancaire(),
            )
        )
        or 0
    )


def dernieres_operations(db: Session, account_ids: list[int], date_to: date, limit: int):
    """Les dernières opérations jusqu'à `date_to`, de la plus récente à la plus ancienne."""
    if not account_ids:
        return []
    ordre = [column.desc() for column in ORDRE_CHRONOLOGIQUE]
    return list(
        db.scalars(
            select(BankTransaction)
            .where(
                BankTransaction.bank_account_id.in_(account_ids),
                BankTransaction.date_operation <= date_to,
            )
            .order_by(*ordre)
            .limit(limit)
        )
    )


def ecritures_simtis(
    db: Session, company_id: int, date_from: date, date_to: date
) -> tuple[int, int]:
    """(exportées, à exporter) : écritures de frais créées par SIMTIS sur la période."""
    rows = db.execute(
        select(AccountingEntry.exportee_le.is_not(None), func.count())
        .where(
            AccountingEntry.company_id == company_id,
            AccountingEntry.origine == "SIMTIS",
            AccountingEntry.date_ecriture.between(date_from, date_to),
        )
        .group_by(AccountingEntry.exportee_le.is_not(None))
    )
    compte = {bool(row[0]): row[1] for row in rows}
    return compte.get(True, 0), compte.get(False, 0)
