"""Rapports (P16.4) : lectures des lignes non rapprochées d'une période."""

from collections.abc import Collection
from datetime import date

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    AccountingEntry,
    BankTransaction,
    ReconciliationMatch,
    ReconciliationMatchItem,
)
from app.repositories.import_repository import ORDRE_CHRONOLOGIQUE

# Lignes non rapprochées (30/10/2026) : non rapprochée ou en proposition (« À vérifier »)
STATUTS_NON_RAPPROCHES = ("Non rapprochée", "À vérifier")


def operations_non_rapprochees(
    db: Session,
    account_id: int,
    date_from: date,
    date_to: date,
    rapprochees_apres: Collection[int] = (),
) -> list[BankTransaction]:
    """Opérations du compte non rapprochées de la période, de la plus ancienne à la plus récente
    dans l'ordre du relevé (02/11/2026), plus celles de `rapprochees_apres` (rapprochées après
    la fin de la période, 07/11/2026) ; les opérations
    en cours « (*) » et celles remplacées par leur définitive sont exclues."""
    return list(
        db.scalars(
            select(BankTransaction)
            .where(
                BankTransaction.bank_account_id == account_id,
                BankTransaction.date_operation.between(date_from, date_to),
                or_(
                    BankTransaction.statut.in_(STATUTS_NON_RAPPROCHES),
                    BankTransaction.id.in_(list(rapprochees_apres)),
                ),
                BankTransaction.en_cours.is_(False),
                BankTransaction.remplacee_par_id.is_(None),
            )
            .order_by(*ORDRE_CHRONOLOGIQUE)
        )
    )


def ecritures_non_rapprochees(
    db: Session,
    account_id: int,
    date_from: date,
    date_to: date,
    rapprochees_apres: Collection[int] = (),
) -> list[AccountingEntry]:
    """Écritures du compte non rapprochées de la période, de la plus ancienne à la plus récente,
    plus celles de `rapprochees_apres` (rapprochées après la fin de la période, 07/11/2026)."""
    return list(
        db.scalars(
            select(AccountingEntry)
            .where(
                AccountingEntry.bank_account_id == account_id,
                AccountingEntry.date_ecriture.between(date_from, date_to),
                or_(
                    AccountingEntry.statut.in_(STATUTS_NON_RAPPROCHES),
                    AccountingEntry.id.in_(list(rapprochees_apres)),
                ),
            )
            .order_by(AccountingEntry.date_ecriture, AccountingEntry.id)
        )
    )


# --- Rapprochements à cheval sur la fin de la période (07/11/2026) --------------------------------


def _lignes_rapprochees(*colonnes, account_id: int) -> Select:
    """Lignes (opération ou écriture) des rapprochements validés actifs du compte."""
    return (
        select(*colonnes)
        .select_from(ReconciliationMatchItem)
        .join(ReconciliationMatch, ReconciliationMatch.id == ReconciliationMatchItem.match_id)
        .outerjoin(
            BankTransaction, BankTransaction.id == ReconciliationMatchItem.bank_transaction_id
        )
        .outerjoin(
            AccountingEntry, AccountingEntry.id == ReconciliationMatchItem.accounting_entry_id
        )
        .where(
            ReconciliationMatch.statut == "Validée",
            ReconciliationMatchItem.actif.is_(True),
            or_(
                BankTransaction.bank_account_id == account_id,
                AccountingEntry.bank_account_id == account_id,
            ),
        )
    )


def rapprochees_apres(
    db: Session, account_id: int, date_from: date, date_to: date
) -> tuple[dict[int, date], dict[int, date]]:
    """Lignes de la période dont le rapprochement validé a une ligne datée après `date_to` : à
    cette date elles ne sont pas encore rapprochées. Renvoie {id opération: date}, {id écriture:
    date}, la date étant celle de la dernière ligne du rapprochement."""
    jour = func.coalesce(BankTransaction.date_operation, AccountingEntry.date_ecriture)
    fins = (
        _lignes_rapprochees(
            ReconciliationMatchItem.match_id, func.max(jour).label("fin"), account_id=account_id
        )
        .group_by(ReconciliationMatchItem.match_id)
        .having(func.max(jour) > date_to)
        .subquery()
    )
    lignes = db.execute(
        _lignes_rapprochees(
            ReconciliationMatchItem.bank_transaction_id,
            ReconciliationMatchItem.accounting_entry_id,
            fins.c.fin,
            account_id=account_id,
        )
        .join(fins, fins.c.match_id == ReconciliationMatchItem.match_id)
        .where(jour.between(date_from, date_to))
    ).all()
    operations = {t: fin for t, _, fin in lignes if t is not None}
    ecritures = {e: fin for _, e, fin in lignes if e is not None}
    return operations, ecritures
