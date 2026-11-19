from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import String, and_, cast, false, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    AccountingEntry,
    AuditLog,
    BankAccount,
    BankAccountBalance,
    BankStatement,
    BankTransaction,
    ImportBatch,
    ReconciliationMatch,
    User,
)

# Entités dont l'identifiant est celui de la société elle-même
ENTITES_SOCIETE = ("company", "saisie_devises", "saisie_previsions")


def add(db: Session, entry: AuditLog) -> AuditLog:
    db.add(entry)
    db.flush()
    return entry


# --- Lecture du journal (P16.2) -------------------------------------------------------------------


def condition_societes(company_ids: Iterable[int]):
    """Entrées rattachées à l'une de ces sociétés (accès par société, 19/11/2026). La société se
    déduit de l'entité ; une action sans société (utilisateur, rôle, banque, session, paramètre) ou
    sur une ligne supprimée depuis n'est rattachée à aucune."""
    ids = list(company_ids)
    if not ids:
        return false()
    comptes = select(BankAccount.id).where(BankAccount.company_id.in_(ids))
    par_entite = {
        "bank_account": select(cast(BankAccount.id, String)).where(BankAccount.company_id.in_(ids)),
        "bank_account_balance": select(cast(BankAccountBalance.id, String)).where(
            BankAccountBalance.bank_account_id.in_(comptes)
        ),
        "bank_statement": select(cast(BankStatement.id, String)).where(
            BankStatement.bank_account_id.in_(comptes)
        ),
        "bank_transaction": select(cast(BankTransaction.id, String)).where(
            BankTransaction.bank_account_id.in_(comptes)
        ),
        "accounting_entry": select(cast(AccountingEntry.id, String)).where(
            AccountingEntry.company_id.in_(ids)
        ),
        "reconciliation_match": select(cast(ReconciliationMatch.id, String)).where(
            ReconciliationMatch.company_id.in_(ids)
        ),
        "import_batch": select(cast(ImportBatch.id, String)).where(ImportBatch.company_id.in_(ids)),
    }
    return or_(
        and_(
            AuditLog.entite.in_(ENTITES_SOCIETE),
            AuditLog.entite_id.in_([str(company_id) for company_id in ids]),
        ),
        *(
            and_(AuditLog.entite == entite, AuditLog.entite_id.in_(sous_requete))
            for entite, sous_requete in par_entite.items()
        ),
    )


def _filtre(
    *,
    user_id: int | None,
    action: str | None,
    entite: str | None,
    entite_id: str | None,
    debut: datetime | None,
    fin: datetime | None,
    societes: frozenset[int] | None = None,
):
    conditions = []
    if societes is not None:
        conditions.append(condition_societes(societes))
    if user_id is not None:
        conditions.append(AuditLog.user_id == user_id)
    if action:
        conditions.append(AuditLog.action == action)
    if entite:
        conditions.append(AuditLog.entite == entite)
    if entite_id:
        conditions.append(AuditLog.entite_id == entite_id)
    if debut is not None:
        conditions.append(AuditLog.created_at >= debut)
    if fin is not None:
        conditions.append(AuditLog.created_at < fin)
    return conditions


def search(db: Session, *, limit: int, offset: int, **filtres) -> tuple[list[AuditLog], int]:
    """Entrées du plus récent au plus ancien (l'identifiant suit l'ordre d'écriture), et leur
    nombre sur tout le filtre."""
    conditions = _filtre(**filtres)
    total = db.scalar(select(func.count()).select_from(AuditLog).where(*conditions)) or 0
    rows = db.scalars(
        select(AuditLog).where(*conditions).order_by(AuditLog.id.desc()).limit(limit).offset(offset)
    )
    return list(rows), total


def get(db: Session, audit_id: int, societes: frozenset[int] | None = None) -> AuditLog | None:
    """L'entrée, ou None si elle n'existe pas ou n'est rattachée à aucune de ces sociétés."""
    if societes is None:
        return db.get(AuditLog, audit_id)
    return db.scalar(select(AuditLog).where(AuditLog.id == audit_id, condition_societes(societes)))


def _sur(societes: frozenset[int] | None) -> list:
    return [] if societes is None else [condition_societes(societes)]


def actions(db: Session, societes: frozenset[int] | None = None) -> list[tuple[str, int]]:
    rows = db.execute(
        select(AuditLog.action, func.count())
        .where(*_sur(societes))
        .group_by(AuditLog.action)
        .order_by(AuditLog.action)
    )
    return [(row[0], row[1]) for row in rows]


def entites(db: Session, societes: frozenset[int] | None = None) -> list[str]:
    return list(
        db.scalars(
            select(AuditLog.entite).where(*_sur(societes)).distinct().order_by(AuditLog.entite)
        )
    )


def user_names(db: Session, user_ids: set[int] | None = None) -> dict[int, str]:
    query = select(User.id, User.nom)
    if user_ids is not None:
        if not user_ids:
            return {}
        query = query.where(User.id.in_(user_ids))
    return {row[0]: row[1] for row in db.execute(query)}
