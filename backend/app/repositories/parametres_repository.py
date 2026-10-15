"""Paramètres (P16.3) : règles de la grille de rapprochement et modèles de mapping."""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import ColumnMapping, ReconciliationRule


def rules(db: Session, *, lock: bool = False) -> list[ReconciliationRule]:
    query = select(ReconciliationRule).order_by(ReconciliationRule.id)
    if lock:
        query = query.with_for_update()
    return list(db.scalars(query))


def mappings(db: Session) -> list[ColumnMapping]:
    return list(
        db.scalars(
            select(ColumnMapping)
            .options(selectinload(ColumnMapping.bank))
            .order_by(ColumnMapping.type, ColumnMapping.nom)
        )
    )


def mapping(db: Session, mapping_id: int) -> ColumnMapping | None:
    return db.get(ColumnMapping, mapping_id)


def delete(db: Session, obj) -> None:
    db.delete(obj)
    db.flush()
