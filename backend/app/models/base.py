from datetime import datetime
from decimal import Decimal
from typing import Annotated

from sqlalchemy import CheckConstraint, DateTime, MetaData, Numeric, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Noms de contraintes explicites : les migrations Alembic restent prévisibles et réversibles.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# Jamais de `float` pour l'argent : NUMERIC en base, Decimal en Python.
Montant = Annotated[Decimal, mapped_column(Numeric(18, 2))]
Taux = Annotated[Decimal, mapped_column(Numeric(18, 6))]


def sql_in(column: str, values: tuple[str, ...]) -> str:
    """Condition SQL `colonne IN ('a', 'b')` pour un CHECK. Les valeurs viennent de `enums.py`."""
    quoted = ", ".join("'" + value.replace("'", "''") + "'" for value in values)
    return f"{column} IN ({quoted})"


def check_in(name: str, column: str, values: tuple[str, ...]) -> CheckConstraint:
    return CheckConstraint(sql_in(column, values), name=name)


class TimestampMixin:
    """Dates de création et de dernière modification, renseignées par la base."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
