"""Lectures et écritures des écritures comptables importées de Sage / SI (P10)."""

from datetime import date
from decimal import Decimal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    AccountingEntry,
    Bank,
    BankAccount,
    ColumnMapping,
    ImportBatch,
    ReconciliationMatchItem,
    User,
)
from app.repositories import reconciliation_repository
from app.services.import_file import HASH_BATCH
from app.services.reconciliation_scoring import TYPES_SAGE


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
    found: set[str] = set()
    # Par paquets : un fichier de 50 000 lignes ne fait pas une requête de 50 000 valeurs
    for start in range(0, len(hashes), HASH_BATCH):
        batch = hashes[start : start + HASH_BATCH]
        query = select(AccountingEntry.hash_ligne).where(
            AccountingEntry.company_id == company_id, AccountingEntry.hash_ligne.in_(batch)
        )
        found.update(db.scalars(query))
    return found


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
    type_operation: str | None = None,
    operation_possible: bool | None = None,
    fenetre_jours: int = 10,
    sens: str | None = None,
) -> Select:
    """Écritures d'UNE société, filtrées (sans ordre ni pagination). `operation_possible`
    (19/10/2026) : True = une opération bancaire libre au montant opposé existe dans la fenêtre,
    False = aucune (écriture sans banque), None = pas de filtre."""
    query = select(AccountingEntry).where(AccountingEntry.company_id == company_id)
    if bank_account_id is not None:
        query = query.where(AccountingEntry.bank_account_id == bank_account_id)
    if date_from is not None:
        query = query.where(AccountingEntry.date_ecriture >= date_from)
    if date_to is not None:
        query = query.where(AccountingEntry.date_ecriture <= date_to)
    if statut is not None:
        query = query.where(AccountingEntry.statut == statut)
    # Débit / Crédit de l'écriture, comme dans Sage (19/10/2026)
    if sens == "Débit":
        query = query.where(AccountingEntry.debit > 0)
    elif sens == "Crédit":
        query = query.where(AccountingEntry.credit > 0)
    if type_operation is not None:
        query = query.where(
            reconciliation_repository.type_condition(
                AccountingEntry.libelle, TYPES_SAGE, type_operation
            )
        )
    if operation_possible is not None:
        existe = reconciliation_repository.operation_possible(fenetre_jours)
        query = query.where(existe if operation_possible else ~existe)
    if q and q.strip():
        pattern = f"%{_escape_like(q.strip())}%"
        columns = (
            AccountingEntry.libelle,
            AccountingEntry.numero_piece,
            AccountingEntry.reference,
            AccountingEntry.tiers,
        )
        query = query.where(
            or_(
                *(column.ilike(pattern, escape="\\") for column in columns),
                # Code de rapprochement (« BP-26-000123 », 13/10/2026)
                AccountingEntry.id.in_(
                    reconciliation_repository.ids_with_code(
                        ReconciliationMatchItem.accounting_entry_id, q
                    )
                ),
            )
        )
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
            # Un import supprimé reste au journal, au statut « Annulé » (23/10/2026)
            ImportBatch.statut.in_(("Confirmé", "Annulé")),
        )
        .order_by(ImportBatch.created_at.desc(), ImportBatch.id.desc())
    )
    return [tuple(row) for row in db.execute(query)]


# --- Suppression d'un import (23/10/2026) --------------------------------------------------------


def entry_ids_of_batch(db: Session, batch_id: int) -> list[int]:
    return list(
        db.scalars(
            select(AccountingEntry.id)
            .where(AccountingEntry.import_batch_id == batch_id)
            .with_for_update()
        )
    )


def periode_of_entries(db: Session, entry_ids: list[int]) -> tuple[date | None, date | None]:
    if not entry_ids:
        return None, None
    row = db.execute(
        select(
            func.min(AccountingEntry.date_ecriture), func.max(AccountingEntry.date_ecriture)
        ).where(AccountingEntry.id.in_(entry_ids))
    ).one()
    return row[0], row[1]


def delete_entries(db: Session, entry_ids: list[int]) -> None:
    """Supprime des écritures importées et les écarts qui les citent."""
    if not entry_ids:
        return
    from sqlalchemy import delete

    from app.models import Discrepancy

    db.execute(delete(Discrepancy).where(Discrepancy.accounting_entry_id.in_(entry_ids)))
    db.execute(delete(AccountingEntry).where(AccountingEntry.id.in_(entry_ids)))


# --- Solde comptable (26/10/2026) ----------------------------------------------------------------


def mouvements_comptables(db: Session, account_id: int, *, apres: date | None, jusqu_au: date):
    """Débits, crédits et montant devise des écritures du compte après `apres` (exclu, toutes si
    None) jusqu'au `jusqu_au` inclus, avec le nombre d'écritures SIMTIS pas encore exportées."""
    from app.services.solde_comptable_service import Mouvements

    conditions = [
        AccountingEntry.bank_account_id == account_id,
        AccountingEntry.date_ecriture <= jusqu_au,
    ]
    if apres is not None:
        conditions.append(AccountingEntry.date_ecriture > apres)
    row = db.execute(
        select(
            func.coalesce(func.sum(AccountingEntry.debit), 0),
            func.coalesce(func.sum(AccountingEntry.credit), 0),
            func.sum(AccountingEntry.montant_devise),
            func.count(),
            func.count().filter(
                AccountingEntry.origine == "SIMTIS", AccountingEntry.exportee_le.is_(None)
            ),
        ).where(*conditions)
    ).one()
    return Mouvements(
        debit=Decimal(row[0]).quantize(Decimal("0.01")),
        credit=Decimal(row[1]).quantize(Decimal("0.01")),
        devise=None if row[2] is None else Decimal(row[2]),
        nb_ecritures=row[3],
        nb_non_exportees=row[4],
    )
