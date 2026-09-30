from collections import Counter
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Base

ModelT = TypeVar("ModelT", bound=Base)


class SeedError(Exception):
    """Erreur attendue d'un seed (message affiché tel quel à l'utilisateur)."""


def get_or_create(
    session: Session,
    model: type[ModelT],
    lookup: dict[str, Any],
    values: dict[str, Any] | None = None,
    created: Counter[str] | None = None,
) -> tuple[ModelT, bool]:
    """Retourne la ligne identifiée par `lookup`, en la créant avec `values` si elle n'existe pas.

    Une ligne existante n'est jamais modifiée. `created` compte les lignes créées, par table.
    """
    existing = session.scalar(select(model).filter_by(**lookup))
    if existing is not None:
        return existing, False

    row = model(**lookup, **(values or {}))
    session.add(row)
    session.flush()
    if created is not None:
        created[model.__tablename__] += 1
    return row, True


def get_by_code(session: Session, model: type[ModelT], code: str) -> ModelT:
    row = session.scalar(select(model).filter_by(code=code))
    if row is None:
        raise SeedError(
            f"{model.__tablename__} « {code} » introuvable : lancer d'abord `python -m app.seeds`."
        )
    return row
