from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, User


def add(db: Session, entry: AuditLog) -> AuditLog:
    db.add(entry)
    db.flush()
    return entry


# --- Lecture du journal (P16.2) -------------------------------------------------------------------


def _filtre(
    *,
    user_id: int | None,
    action: str | None,
    entite: str | None,
    entite_id: str | None,
    debut: datetime | None,
    fin: datetime | None,
):
    conditions = []
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


def get(db: Session, audit_id: int) -> AuditLog | None:
    return db.get(AuditLog, audit_id)


def actions(db: Session) -> list[tuple[str, int]]:
    rows = db.execute(
        select(AuditLog.action, func.count()).group_by(AuditLog.action).order_by(AuditLog.action)
    )
    return [(row[0], row[1]) for row in rows]


def entites(db: Session) -> list[str]:
    return list(db.scalars(select(AuditLog.entite).distinct().order_by(AuditLog.entite)))


def user_names(db: Session, user_ids: set[int] | None = None) -> dict[int, str]:
    query = select(User.id, User.nom)
    if user_ids is not None:
        if not user_ids:
            return {}
        query = query.where(User.id.in_(user_ids))
    return {row[0]: row[1] for row in db.execute(query)}
