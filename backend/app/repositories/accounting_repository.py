"""Lectures et écritures des écritures comptables importées de Sage / SI (P10)."""

from datetime import date
from decimal import Decimal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models import AccountingEntry, Bank, BankAccount, ColumnMapping, ImportBatch, User


def bank_journals(db: Session, company_id: int) -> list[BankAccount]:
    """Comptes bancaires actifs de la société qui ont un journal Sage."""
    query = select(BankAccount).where(
        BankAccount.company_id == company_id,
        BankAccount.actif.is_(True),
        BankAccount.journal_sage.is_not(None),
    )
    return list(db.scalars(query))


def existing_entry_hashes(db: Session, company_id: int, hashes: list[str]) -> set[str]:
    """Empreintes déjà enregistrées pour la société, parmi celles demandées."""
    if not hashes:
        return set()
    query = select(AccountingEntry.hash_ligne).where(
        AccountingEntry.company_id == company_id, AccountingEntry.hash_ligne.in_(hashes)
    )
    return set(db.scalars(query))


def latest_company_mapping(db: Session, company_id: int, type_import: str) -> ColumnMapping | None:
    """Dernier modèle de correspondance mémorisé pour une société."""
    query = (
        select(ColumnMapping)
        .where(ColumnMapping.company_id == company_id, ColumnMapping.type == type_import)
        .order_by(ColumnMapping.updated_at.desc(), ColumnMapping.id.desc())
        .limit(1)
    )
    return db.scalar(query)


def add(db: Session, row: object) -> None:
    db.add(row)


def _escape_like(text: str) -> str:
    """`%` et `_` cherchés comme des caractères, pas comme des jokers SQL."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def entries_query(
    company_id: int,
    *,
    bank_account_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    statut: str | None = None,
    q: str | None = None,
) -> Select:
    """Écritures d'UNE société, filtrées (sans ordre ni pagination)."""
    query = select(AccountingEntry).where(AccountingEntry.company_id == company_id)
    if bank_account_id is not None:
        query = query.where(AccountingEntry.bank_account_id == bank_account_id)
    if date_from is not None:
        query = query.where(AccountingEntry.date_ecriture >= date_from)
    if date_to is not None:
        query = query.where(AccountingEntry.date_ecriture <= date_to)
    if statut is not None:
        query = query.where(AccountingEntry.statut == statut)
    if q and q.strip():
        pattern = f"%{_escape_like(q.strip())}%"
        columns = (
            AccountingEntry.libelle,
            AccountingEntry.numero_piece,
            AccountingEntry.reference,
            AccountingEntry.tiers,
        )
        query = query.where(or_(*(column.ilike(pattern, escape="\\") for column in columns)))
    return query


def page_of_entries(
    db: Session, query: Select, *, offset: int, limit: int
) -> list[tuple[AccountingEntry, str | None]]:
    """Une page d'écritures, de la plus récente à la plus ancienne, avec le code de leur banque."""
    filtered = query.subquery()
    rows = db.execute(
        select(AccountingEntry, Bank.code)
        .join(filtered, filtered.c.id == AccountingEntry.id)
        .outerjoin(BankAccount, BankAccount.id == AccountingEntry.bank_account_id)
        .outerjoin(Bank, Bank.id == BankAccount.bank_id)
        .order_by(AccountingEntry.date_ecriture.desc(), AccountingEntry.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return [(row[0], row[1]) for row in rows]


def totals_of_entries(db: Session, query: Select) -> tuple[int, Decimal, Decimal]:
    """Nombre d'écritures et totaux débit / crédit sur tout le filtre."""
    filtered = query.subquery()
    total, debit, credit = db.execute(
        select(
            func.count(),
            func.coalesce(func.sum(filtered.c.debit), 0),
            func.coalesce(func.sum(filtered.c.credit), 0),
        )
    ).one()
    return total, Decimal(debit), Decimal(credit)


def get_entry(
    db: Session, entry_id: int
) -> tuple[AccountingEntry, str | None, ImportBatch | None, str | None] | None:
    """Une écriture, le code de sa banque, son import et l'auteur de l'import."""
    row = db.execute(
        select(AccountingEntry, Bank.code, ImportBatch, User.nom)
        .outerjoin(BankAccount, BankAccount.id == AccountingEntry.bank_account_id)
        .outerjoin(Bank, Bank.id == BankAccount.bank_id)
        .outerjoin(ImportBatch, ImportBatch.id == AccountingEntry.import_batch_id)
        .outerjoin(User, User.id == ImportBatch.user_id)
        .where(AccountingEntry.id == entry_id)
    ).first()
    return None if row is None else (row[0], row[1], row[2], row[3])


def list_imports(
    db: Session, company_id: int, type_import: str
) -> list[
    tuple[
        ImportBatch,
        str | None,
        date | None,
        date | None,
        int | None,
        Decimal | None,
        Decimal | None,
    ]
]:
    """Imports comptables confirmés de la société, du plus récent au plus ancien, avec leur
    auteur, leur période et leurs totaux."""
    stats = (
        select(
            AccountingEntry.import_batch_id.label("batch_id"),
            func.min(AccountingEntry.date_ecriture).label("debut"),
            func.max(AccountingEntry.date_ecriture).label("fin"),
            func.count().label("nb"),
            func.sum(AccountingEntry.debit).label("debit"),
            func.sum(AccountingEntry.credit).label("credit"),
        )
        .group_by(AccountingEntry.import_batch_id)
        .subquery()
    )
    query = (
        select(
            ImportBatch,
            User.nom,
            stats.c.debut,
            stats.c.fin,
            stats.c.nb,
            stats.c.debit,
            stats.c.credit,
        )
        .outerjoin(stats, stats.c.batch_id == ImportBatch.id)
        .outerjoin(User, User.id == ImportBatch.user_id)
        .where(
            ImportBatch.company_id == company_id,
            ImportBatch.type == type_import,
            ImportBatch.statut == "Confirmé",
        )
        .order_by(ImportBatch.created_at.desc(), ImportBatch.id.desc())
    )
    return [tuple(row) for row in db.execute(query)]
