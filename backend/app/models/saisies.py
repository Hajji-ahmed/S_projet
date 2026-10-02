"""Tableaux Devises et Prévisions saisis à la main, cellule par cellule (page Position bancaire).

Première version, en attendant les imports et les calculs (P9, P14) : chaque cellule du classeur est
une valeur saisie pour une société et une date. Rien n'y est calculé.
"""

from datetime import date

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Identity,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models import enums
from app.models.base import Base, Montant, TimestampMixin, check_in


class SaisieDevise(TimestampMixin, Base):
    """Une cellule du tableau Devises : ligne EUR / USD / Exp DH convertible, colonne banque ou
    TOTAL / DEPASSEMENT. Une cellule vide n'a pas de ligne en base (jamais un 0)."""

    __tablename__ = "saisies_devises"
    __table_args__ = (
        check_in("ligne", "ligne", enums.LIGNES_DEVISES),
        check_in("colonne", "colonne", enums.COLONNES_DEVISES),
        CheckConstraint(
            "(colonne = 'Banque') = (bank_id IS NOT NULL)", name="banque_si_colonne_banque"
        ),
        # Une seule valeur par cellule : une par banque, et une par colonne hors banques
        Index(
            "uq_saisies_devises_cellule_banque",
            "company_id",
            "jour",
            "ligne",
            "bank_id",
            unique=True,
            postgresql_where=text("bank_id IS NOT NULL"),
        ),
        Index(
            "uq_saisies_devises_cellule_colonne",
            "company_id",
            "jour",
            "ligne",
            "colonne",
            unique=True,
            postgresql_where=text("bank_id IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    jour: Mapped[date] = mapped_column(Date)
    ligne: Mapped[str] = mapped_column(String(20))
    colonne: Mapped[str] = mapped_column(String(12))
    bank_id: Mapped[int | None] = mapped_column(ForeignKey("banks.id"), index=True)
    montant: Mapped[Montant]
    saisi_par_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class SaisiePrevision(TimestampMixin, Base):
    """Une cellule des 14 lignes du tableau Prévisions : le libellé de la ligne (sans banque) ou le
    montant d'une banque."""

    __tablename__ = "saisies_previsions"
    __table_args__ = (
        CheckConstraint(f"ligne BETWEEN 1 AND {enums.NB_LIGNES_PREVISIONS}", name="ligne_du_bloc"),
        CheckConstraint(
            "(bank_id IS NULL AND libelle IS NOT NULL AND montant IS NULL)"
            " OR (bank_id IS NOT NULL AND montant IS NOT NULL AND libelle IS NULL)",
            name="libelle_ou_montant",
        ),
        Index(
            "uq_saisies_previsions_cellule_banque",
            "company_id",
            "jour",
            "ligne",
            "bank_id",
            unique=True,
            postgresql_where=text("bank_id IS NOT NULL"),
        ),
        Index(
            "uq_saisies_previsions_libelle",
            "company_id",
            "jour",
            "ligne",
            unique=True,
            postgresql_where=text("bank_id IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    jour: Mapped[date] = mapped_column(Date)
    ligne: Mapped[int] = mapped_column(SmallInteger)
    bank_id: Mapped[int | None] = mapped_column(ForeignKey("banks.id"), index=True)
    libelle: Mapped[str | None] = mapped_column(String(80))
    montant: Mapped[Montant | None]
    saisi_par_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class SaisiePrevisionJour(TimestampMixin, Base):
    """Les trois cellules fusionnées du tableau Prévisions : montants de la journée, sans banque."""

    __tablename__ = "saisies_previsions_jour"
    __table_args__ = (
        UniqueConstraint("company_id", "jour", name="uq_saisies_previsions_jour_societe_jour"),
        # Trois cellules vides : la ligne est supprimée, jamais gardée avec des 0
        CheckConstraint(
            "encaissement IS NOT NULL OR escompte IS NOT NULL OR douane IS NOT NULL",
            name="un_montant_renseigne",
        ),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    jour: Mapped[date] = mapped_column(Date)
    encaissement: Mapped[Montant | None]
    escompte: Mapped[Montant | None]
    douane: Mapped[Montant | None]
    saisi_par_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
