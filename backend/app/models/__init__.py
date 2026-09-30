"""Modèles ORM (SQLAlchemy). Importer ici chaque nouveau modèle pour qu'Alembic le détecte."""

from app.models.base import Base

__all__ = ["Base"]
