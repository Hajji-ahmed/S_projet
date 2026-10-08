from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BalanceCheck,
    BankAccount,
    BankAccountBalance,
    BankStatement,
    BankTransaction,
    ColumnMapping,
    ImportBatch,
    PointageType,
    User,
)
from app.services.import_file import HASH_BATCH


def existing_line_hashes(db: Session, account_id: int, hashes: list[str]) -> set[str]:
    """Empreintes déjà enregistrées pour ce compte, parmi celles demandées."""
    found: set[str] = set()
    # Par paquets : un fichier de 50 000 lignes ne fait pas une requête de 50 000 valeurs
    for start in range(0, len(hashes), HASH_BATCH):
        batch = hashes[start : start + HASH_BATCH]
        query = select(BankTransaction.hash_ligne).where(
            BankTransaction.bank_account_id == account_id, BankTransaction.hash_ligne.in_(batch)
        )
        found.update(db.scalars(query))
    return found


def confirmed_file(
    db: Session, company_id: int, type_import: str, fichier_hash: str
) -> ImportBatch | None:
    query = select(ImportBatch).where(
        ImportBatch.company_id == company_id,
        ImportBatch.type == type_import,
        ImportBatch.fichier_hash == fichier_hash,
        ImportBatch.statut == "Confirmé",
    )
    return db.scalar(query)


def latest_mapping(db: Session, bank_id: int, type_import: str) -> ColumnMapping | None:
    """Dernier modèle de correspondance mémorisé pour une banque."""
    query = (
        select(ColumnMapping)
        .where(ColumnMapping.bank_id == bank_id, ColumnMapping.type == type_import)
        .order_by(ColumnMapping.updated_at.desc(), ColumnMapping.id.desc())
        .limit(1)
    )
    return db.scalar(query)


def active_pointage_types(db: Session) -> list[PointageType]:
    return list(db.scalars(select(PointageType).where(PointageType.actif.is_(True))))


def list_statements(
    db: Session, company_id: int, bank_account_id: int | None = None
) -> list[tuple[BankStatement, ImportBatch, BankAccount, str | None]]:
    """Relevés importés d'une société, du plus récent au plus ancien, avec l'auteur de l'import."""
    query = (
        select(BankStatement, ImportBatch, BankAccount, User.nom)
        .join(ImportBatch, ImportBatch.id == BankStatement.import_batch_id)
        .join(BankAccount, BankAccount.id == BankStatement.bank_account_id)
        .outerjoin(User, User.id == ImportBatch.user_id)
        .where(BankAccount.company_id == company_id)
        .order_by(ImportBatch.created_at.desc(), ImportBatch.id.desc())
    )
    if bank_account_id is not None:
        query = query.where(BankStatement.bank_account_id == bank_account_id)
    return [tuple(row) for row in db.execute(query)]


def balance_checks(db: Session, statement_ids: list[int]) -> dict[int, BalanceCheck]:
    if not statement_ids:
        return {}
    query = select(BalanceCheck).where(BalanceCheck.bank_statement_id.in_(statement_ids))
    return {check.bank_statement_id: check for check in db.scalars(query)}


def get_statement(db: Session, statement_id: int) -> BankStatement | None:
    return db.get(BankStatement, statement_id)


def statement_transactions(
    db: Session, statement_id: int
) -> list[tuple[BankTransaction, str | None]]:
    """Opérations d'un relevé, dans l'ordre chronologique, avec le libellé de leur pointage."""
    query = (
        select(BankTransaction, PointageType.libelle)
        .outerjoin(PointageType, PointageType.id == BankTransaction.pointage_type_id)
        .where(BankTransaction.statement_id == statement_id)
        .order_by(BankTransaction.date_operation, BankTransaction.id)
    )
    return [(row, pointage) for row, pointage in db.execute(query)]


def account_transactions(
    db: Session, account_id: int, date_from: date | None, date_to: date | None
) -> list[tuple[BankTransaction, str | None]]:
    """Toutes les opérations importées d'un compte, quel que soit le fichier : par date, puis dans
    l'ordre d'import. Avec le libellé de leur pointage."""
    query = (
        select(BankTransaction, PointageType.libelle)
        .outerjoin(PointageType, PointageType.id == BankTransaction.pointage_type_id)
        .where(BankTransaction.bank_account_id == account_id)
        .order_by(BankTransaction.date_operation, BankTransaction.id)
    )
    if date_from is not None:
        query = query.where(BankTransaction.date_operation >= date_from)
    if date_to is not None:
        query = query.where(BankTransaction.date_operation <= date_to)
    return [(row, pointage) for row, pointage in db.execute(query)]


def get_transaction(db: Session, transaction_id: int) -> BankTransaction | None:
    return db.get(BankTransaction, transaction_id)


def get_pointage_type(db: Session, pointage_type_id: int) -> PointageType | None:
    return db.get(PointageType, pointage_type_id)


def add(db: Session, *rows: object) -> None:
    """Ajoute les lignes et les envoie à la base (les identifiants deviennent disponibles)."""
    db.add_all(rows)
    db.flush()


def pointages_of_company(db: Session, company_id: int) -> list[tuple[str, int]]:
    """(libellé, pointage) des opérations de la société qui ont un pointage encore actif : la
    mémoire du pointage automatique."""
    rows = db.execute(
        select(BankTransaction.libelle, BankTransaction.pointage_type_id)
        .join(BankAccount, BankAccount.id == BankTransaction.bank_account_id)
        .join(PointageType, PointageType.id == BankTransaction.pointage_type_id)
        .where(BankAccount.company_id == company_id, PointageType.actif.is_(True))
    )
    return [(row[0], row[1]) for row in rows]


def last_known_balance(
    db: Session, account_id: int, before: date
) -> tuple[date, Decimal, str] | None:
    """Dernier solde connu du compte avant une date : (jour, solde, origine), le plus récent entre
    la dernière opération importée qui porte un solde et le dernier solde du jour enregistré ; à
    date égale, l'opération l'emporte."""
    operation = db.execute(
        select(BankTransaction.date_operation, BankTransaction.solde)
        .where(
            BankTransaction.bank_account_id == account_id,
            BankTransaction.date_operation < before,
            BankTransaction.solde.is_not(None),
        )
        .order_by(BankTransaction.date_operation.desc(), BankTransaction.id.desc())
        .limit(1)
    ).first()
    balance = db.execute(
        select(BankAccountBalance.date_solde, BankAccountBalance.solde)
        .where(
            BankAccountBalance.bank_account_id == account_id,
            BankAccountBalance.date_solde < before,
        )
        .order_by(BankAccountBalance.date_solde.desc())
        .limit(1)
    ).first()
    if operation is not None and (balance is None or operation[0] >= balance[0]):
        return operation[0], operation[1], "operation"
    if balance is not None:
        return balance[0], balance[1], "solde"
    return None


def statement_transactions_in_order(db: Session, statement_id: int) -> list[BankTransaction]:
    """Opérations d'un relevé, par date puis ordre d'import."""
    query = (
        select(BankTransaction)
        .where(BankTransaction.statement_id == statement_id)
        .order_by(BankTransaction.date_operation, BankTransaction.id)
    )
    return list(db.scalars(query))
