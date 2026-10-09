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


# Ordre chronologique des opérations d'un compte : par date, puis relevé (ordre d'import), puis rang
# dans le relevé (`ordre`, 08/10/2026), puis id pour les lignes créées sans rang
ORDRE_CHRONOLOGIQUE = (
    BankTransaction.date_operation,
    BankTransaction.statement_id,
    BankTransaction.ordre,
    BankTransaction.id,
)
ORDRE_ANTECHRONOLOGIQUE = tuple(colonne.desc() for colonne in ORDRE_CHRONOLOGIQUE)


def statement_transactions(
    db: Session, statement_id: int
) -> list[tuple[BankTransaction, str | None]]:
    """Opérations d'un relevé, dans l'ordre chronologique, avec le libellé de leur pointage."""
    query = (
        select(BankTransaction, PointageType.libelle)
        .outerjoin(PointageType, PointageType.id == BankTransaction.pointage_type_id)
        .where(BankTransaction.statement_id == statement_id)
        .order_by(*ORDRE_CHRONOLOGIQUE)
    )
    return [(row, pointage) for row, pointage in db.execute(query)]


def account_transactions(
    db: Session, account_id: int, date_from: date | None, date_to: date | None
) -> list[tuple[BankTransaction, str | None]]:
    """Toutes les opérations importées d'un compte, quel que soit le fichier, dans l'ordre
    chronologique (`ORDRE_CHRONOLOGIQUE`). Avec le libellé de leur pointage."""
    query = (
        select(BankTransaction, PointageType.libelle)
        .outerjoin(PointageType, PointageType.id == BankTransaction.pointage_type_id)
        .where(BankTransaction.bank_account_id == account_id)
        .order_by(*ORDRE_CHRONOLOGIQUE)
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
        .order_by(*ORDRE_ANTECHRONOLOGIQUE)
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
    # Un compte alimenté par un relevé ne lit que son relevé (08/10/2026)
    if operation is not None:
        return operation[0], operation[1], "operation"
    if balance is not None:
        return balance[0], balance[1], "solde"
    return None


def statement_transactions_in_order(db: Session, statement_id: int) -> list[BankTransaction]:
    """Opérations d'un relevé, dans l'ordre chronologique."""
    query = (
        select(BankTransaction)
        .where(BankTransaction.statement_id == statement_id)
        .order_by(*ORDRE_CHRONOLOGIQUE)
    )
    return list(db.scalars(query))


def first_balance_from(db: Session, account_id: int, day: date) -> tuple[date, Decimal] | None:
    """Premier solde du jour enregistré (tableau Banques) à partir de `day` inclus : (jour, solde)."""
    row = db.execute(
        select(BankAccountBalance.date_solde, BankAccountBalance.solde)
        .where(
            BankAccountBalance.bank_account_id == account_id,
            BankAccountBalance.date_solde >= day,
        )
        .order_by(BankAccountBalance.date_solde)
        .limit(1)
    ).first()
    return None if row is None else (row[0], row[1])


def last_operation_before(
    db: Session, account_id: int, before: date
) -> tuple[date, Decimal] | None:
    """(jour, solde) de la dernière opération importée avant `before` qui porte un solde, dans
    l'ordre chronologique : le solde de clôture du relevé précédent."""
    row = db.execute(
        select(BankTransaction.date_operation, BankTransaction.solde)
        .where(
            BankTransaction.bank_account_id == account_id,
            BankTransaction.date_operation < before,
            BankTransaction.solde.is_not(None),
        )
        .order_by(*ORDRE_ANTECHRONOLOGIQUE)
        .limit(1)
    ).first()
    return None if row is None else (row[0], row[1])
