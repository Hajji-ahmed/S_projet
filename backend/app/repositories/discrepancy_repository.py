"""Lectures et écritures des écarts (P12)."""

from datetime import date
from decimal import Decimal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.models import (
    AccountingEntry,
    AuditLog,
    Bank,
    BankAccount,
    BankTransaction,
    Discrepancy,
    Permission,
    ReconciliationMatchItem,
    Role,
    User,
)

STATUTS_OUVERTS = ("À traiter", "En cours", "Traité")


def add(db: Session, row: object) -> None:
    db.add(row)


def get(db: Session, discrepancy_id: int, *, lock: bool = False) -> Discrepancy | None:
    query = select(Discrepancy).where(Discrepancy.id == discrepancy_id)
    if lock:
        query = query.with_for_update()
    return db.scalar(query)


def open_discrepancy_of(
    db: Session, *, transaction_id: int | None = None, entry_id: int | None = None
) -> Discrepancy | None:
    """Écart ouvert (non clôturé) de l'opération ou de l'écriture."""
    conditions = []
    if transaction_id is not None:
        conditions.append(Discrepancy.bank_transaction_id == transaction_id)
    if entry_id is not None:
        conditions.append(Discrepancy.accounting_entry_id == entry_id)
    if not conditions:
        return None
    return db.scalar(
        select(Discrepancy).where(Discrepancy.statut != "Clôturé", or_(*conditions)).limit(1)
    )


def open_discrepancy_by_transaction(db: Session, transaction_ids: list[int]) -> dict[int, int]:
    """Identifiant de l'écart ouvert de chaque opération demandée."""
    if not transaction_ids:
        return {}
    rows = db.execute(
        select(Discrepancy.bank_transaction_id, Discrepancy.id).where(
            Discrepancy.statut != "Clôturé",
            Discrepancy.bank_transaction_id.in_(transaction_ids),
        )
    )
    return {row[0]: row[1] for row in rows}


def _active_match_transactions() -> Select:
    return select(ReconciliationMatchItem.bank_transaction_id).where(
        ReconciliationMatchItem.actif.is_(True),
        ReconciliationMatchItem.bank_transaction_id.is_not(None),
    )


def _active_match_entries() -> Select:
    return select(ReconciliationMatchItem.accounting_entry_id).where(
        ReconciliationMatchItem.actif.is_(True),
        ReconciliationMatchItem.accounting_entry_id.is_not(None),
    )


def _transactions_with_discrepancy() -> Select:
    return select(Discrepancy.bank_transaction_id).where(
        Discrepancy.bank_transaction_id.is_not(None)
    )


def _entries_with_discrepancy() -> Select:
    return select(Discrepancy.accounting_entry_id).where(
        Discrepancy.accounting_entry_id.is_not(None)
    )


# --- Génération -----------------------------------------------------------------------------------


def unmatched_transactions(
    db: Session, account_ids: list[int], date_from: date, date_to: date
) -> list[BankTransaction]:
    """Opérations « Non rapprochée » de la période, hors correspondance active, qui n'ont jamais eu
    d'écart."""
    query = (
        select(BankTransaction)
        .where(
            BankTransaction.bank_account_id.in_(account_ids),
            BankTransaction.date_operation >= date_from,
            BankTransaction.date_operation <= date_to,
            BankTransaction.statut == "Non rapprochée",
            BankTransaction.id.not_in(_active_match_transactions()),
            BankTransaction.id.not_in(_transactions_with_discrepancy()),
        )
        .order_by(BankTransaction.date_operation, BankTransaction.id)
    )
    return list(db.scalars(query))


def unmatched_entries(
    db: Session, company_id: int, account_ids: list[int], date_from: date, date_to: date
) -> list[AccountingEntry]:
    """Écritures « Non rapprochée » de la période, hors correspondance active, qui n'ont jamais eu
    d'écart."""
    query = (
        select(AccountingEntry)
        .where(
            AccountingEntry.company_id == company_id,
            AccountingEntry.bank_account_id.in_(account_ids),
            AccountingEntry.date_ecriture >= date_from,
            AccountingEntry.date_ecriture <= date_to,
            AccountingEntry.statut == "Non rapprochée",
            AccountingEntry.id.not_in(_active_match_entries()),
            AccountingEntry.id.not_in(_entries_with_discrepancy()),
        )
        .order_by(AccountingEntry.date_ecriture, AccountingEntry.id)
    )
    return list(db.scalars(query))


def transactions_of_period(
    db: Session, account_ids: list[int], date_from: date, date_to: date
) -> list[BankTransaction]:
    """Toutes les opérations de la période (recherche des doublons)."""
    query = (
        select(BankTransaction)
        .where(
            BankTransaction.bank_account_id.in_(account_ids),
            BankTransaction.date_operation >= date_from,
            BankTransaction.date_operation <= date_to,
        )
        .order_by(BankTransaction.id)
    )
    return list(db.scalars(query))


def entries_of_period(
    db: Session, company_id: int, account_ids: list[int], date_from: date, date_to: date
) -> list[AccountingEntry]:
    """Toutes les écritures de la période (recherche des doublons)."""
    query = (
        select(AccountingEntry)
        .where(
            AccountingEntry.company_id == company_id,
            AccountingEntry.bank_account_id.in_(account_ids),
            AccountingEntry.date_ecriture >= date_from,
            AccountingEntry.date_ecriture <= date_to,
        )
        .order_by(AccountingEntry.id)
    )
    return list(db.scalars(query))


def transaction_ids_in_active_match(db: Session, ids: list[int]) -> set[int]:
    if not ids:
        return set()
    query = _active_match_transactions().where(ReconciliationMatchItem.bank_transaction_id.in_(ids))
    return set(db.scalars(query))


def entry_ids_in_active_match(db: Session, ids: list[int]) -> set[int]:
    if not ids:
        return set()
    query = _active_match_entries().where(ReconciliationMatchItem.accounting_entry_id.in_(ids))
    return set(db.scalars(query))


def transaction_ids_with_discrepancy(db: Session, ids: list[int]) -> set[int]:
    if not ids:
        return set()
    query = _transactions_with_discrepancy().where(Discrepancy.bank_transaction_id.in_(ids))
    return set(db.scalars(query))


def entry_ids_with_discrepancy(db: Session, ids: list[int]) -> set[int]:
    if not ids:
        return set()
    query = _entries_with_discrepancy().where(Discrepancy.accounting_entry_id.in_(ids))
    return set(db.scalars(query))


# --- Lecture --------------------------------------------------------------------------------------

_Tx = aliased(BankTransaction)
_Entry = aliased(AccountingEntry)
_Account = aliased(BankAccount)
_Bank = aliased(Bank)
_Responsable = aliased(User)


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _account_id():
    """Compte de l'écart : celui de son opération, sinon celui de son écriture."""
    return func.coalesce(_Tx.bank_account_id, _Entry.bank_account_id)


def discrepancies_query(
    company_id: int,
    *,
    bank_account_id: int | None = None,
    type_ecart: str | None = None,
    responsable_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    q: str | None = None,
) -> Select:
    """Écarts d'UNE société, filtrés, sans filtre de statut (ni ordre, ni pagination)."""
    query = (
        select(Discrepancy.id)
        .outerjoin(_Tx, _Tx.id == Discrepancy.bank_transaction_id)
        .outerjoin(_Entry, _Entry.id == Discrepancy.accounting_entry_id)
        .where(Discrepancy.company_id == company_id)
    )
    if bank_account_id is not None:
        query = query.where(_account_id() == bank_account_id)
    if type_ecart is not None:
        query = query.where(Discrepancy.type == type_ecart)
    if responsable_id is not None:
        query = query.where(Discrepancy.responsable_id == responsable_id)
    if date_from is not None:
        query = query.where(Discrepancy.date_ecart >= date_from)
    if date_to is not None:
        query = query.where(Discrepancy.date_ecart <= date_to)
    if q and q.strip():
        pattern = f"%{_escape_like(q.strip())}%"
        columns = (
            _Tx.libelle,
            _Tx.reference,
            _Entry.libelle,
            _Entry.numero_piece,
            _Entry.tiers,
            Discrepancy.commentaire,
        )
        query = query.where(or_(*(column.ilike(pattern, escape="\\") for column in columns)))
    return query


def count_by_status(db: Session, ids_query: Select) -> dict[str, int]:
    ids = ids_query.subquery()
    rows = db.execute(
        select(Discrepancy.statut, func.count())
        .join(ids, ids.c.id == Discrepancy.id)
        .group_by(Discrepancy.statut)
    )
    return {row[0]: row[1] for row in rows}


def open_totals_by_currency(db: Session, ids_query: Select) -> dict[str, Decimal]:
    """Montant des écarts ouverts, par devise du compte (jamais additionné entre devises)."""
    ids = ids_query.subquery()
    rows = db.execute(
        select(_Account.devise, func.sum(Discrepancy.montant))
        .join(ids, ids.c.id == Discrepancy.id)
        .outerjoin(_Tx, _Tx.id == Discrepancy.bank_transaction_id)
        .outerjoin(_Entry, _Entry.id == Discrepancy.accounting_entry_id)
        .join(_Account, _Account.id == _account_id())
        .where(Discrepancy.statut.in_(STATUTS_OUVERTS))
        .group_by(_Account.devise)
    )
    return {row[0]: Decimal(row[1]) for row in rows}


Row = tuple[
    Discrepancy,
    BankTransaction | None,
    AccountingEntry | None,
    str | None,
    str | None,
    str | None,
]


def page(
    db: Session, ids_query: Select, *, statut: str | None, offset: int, limit: int
) -> tuple[int, list[Row]]:
    """Nombre d'écarts du filtre et une page, des plus récents aux plus anciens.

    Chaque ligne : écart, opération, écriture, code banque, devise du compte, nom du responsable.
    """
    if statut is not None:
        ids_query = ids_query.where(Discrepancy.statut == statut)
    ids = ids_query.subquery()
    total = db.scalar(select(func.count()).select_from(ids)) or 0
    rows = db.execute(
        _detail_select()
        .join(ids, ids.c.id == Discrepancy.id)
        .order_by(Discrepancy.date_ecart.desc(), Discrepancy.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return total, [tuple(row) for row in rows]


def _detail_select() -> Select:
    return (
        select(Discrepancy, _Tx, _Entry, _Bank.code, _Account.devise, _Responsable.nom)
        .outerjoin(_Tx, _Tx.id == Discrepancy.bank_transaction_id)
        .outerjoin(_Entry, _Entry.id == Discrepancy.accounting_entry_id)
        .outerjoin(_Account, _Account.id == _account_id())
        .outerjoin(_Bank, _Bank.id == _Account.bank_id)
        .outerjoin(_Responsable, _Responsable.id == Discrepancy.responsable_id)
    )


def detail(db: Session, discrepancy_id: int) -> Row | None:
    row = db.execute(_detail_select().where(Discrepancy.id == discrepancy_id)).first()
    return None if row is None else tuple(row)


def history(db: Session, discrepancy_id: int) -> list[tuple[AuditLog, str | None]]:
    """Journal d'un écart, du plus ancien au plus récent, avec le nom de l'auteur."""
    rows = db.execute(
        select(AuditLog, User.nom)
        .outerjoin(User, User.id == AuditLog.user_id)
        .where(AuditLog.entite == "discrepancy", AuditLog.entite_id == str(discrepancy_id))
        .order_by(AuditLog.created_at, AuditLog.id)
    )
    return [(row[0], row[1]) for row in rows]


def user_name(db: Session, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    return db.scalar(select(User.nom).where(User.id == user_id))


def responsables(db: Session, permission_code: str) -> list[User]:
    """Utilisateurs actifs qui ont la permission (par l'un de leurs rôles)."""
    with_permission = (
        select(User.id)
        .join(User.roles)
        .join(Role.permissions)
        .where(Permission.code == permission_code)
    )
    query = (
        select(User).where(User.actif.is_(True), User.id.in_(with_permission)).order_by(User.nom)
    )
    return list(db.scalars(query))
