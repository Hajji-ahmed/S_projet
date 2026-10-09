"""Imports de fichiers, relevés bancaires, transactions et écritures comptables."""

from datetime import date
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import enums
from app.models.base import Base, Montant, TimestampMixin, check_in
from app.models.referentiel import Bank, BankAccount, Company, PointageType


class ImportBatch(TimestampMixin, Base):
    """Un fichier importé (relevé bancaire ou export comptable). Circuit en 2 temps : analyse, puis confirmation."""

    __tablename__ = "import_batches"
    __table_args__ = (
        check_in("type", "type", enums.TYPES_IMPORT),
        check_in("statut", "statut", enums.STATUTS_IMPORT),
        # Un même fichier (même contenu) ne peut être confirmé qu'une seule fois par société et par type
        Index(
            "uq_import_batches_fichier_confirme",
            "company_id",
            "type",
            "fichier_hash",
            unique=True,
            postgresql_where=text("statut = 'Confirmé'"),
        ),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    type: Mapped[str] = mapped_column(String(15))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    bank_account_id: Mapped[int | None] = mapped_column(ForeignKey("bank_accounts.id"))
    fichier_nom: Mapped[str] = mapped_column(String(255))
    fichier_hash: Mapped[str] = mapped_column(String(64))
    statut: Mapped[str] = mapped_column(String(15), default="Analysé", server_default="Analysé")
    nb_lignes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    nb_erreurs: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    nb_doublons: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class ColumnMapping(TimestampMixin, Base):
    """Modèle de correspondance colonnes du fichier → champs standard, mémorisé par banque."""

    __tablename__ = "column_mappings"
    __table_args__ = (check_in("type", "type", enums.TYPES_IMPORT),)

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    type: Mapped[str] = mapped_column(String(15))
    bank_id: Mapped[int | None] = mapped_column(ForeignKey("banks.id"))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"))
    nom: Mapped[str] = mapped_column(String(120))
    mapping: Mapped[dict[str, Any]] = mapped_column(JSONB)
    format_date: Mapped[str | None] = mapped_column(String(30))
    separateur_decimal: Mapped[str | None] = mapped_column(String(1))

    bank: Mapped[Bank | None] = relationship()


class BankStatement(TimestampMixin, Base):
    """Relevé bancaire importé pour un compte et une période."""

    __tablename__ = "bank_statements"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    bank_account_id: Mapped[int] = mapped_column(ForeignKey("bank_accounts.id"), index=True)
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batches.id"))
    periode_debut: Mapped[date | None] = mapped_column(Date)
    periode_fin: Mapped[date | None] = mapped_column(Date)
    solde_ouverture: Mapped[Montant | None]
    solde_cloture: Mapped[Montant | None]

    bank_account: Mapped[BankAccount] = relationship()


class BankTransaction(TimestampMixin, Base):
    """Mouvement bancaire normalisé. `montant` = crédit − débit (positif = entrée d'argent)."""

    __tablename__ = "bank_transactions"
    __table_args__ = (
        UniqueConstraint("bank_account_id", "hash_ligne", name="uq_bank_transactions_compte_hash"),
        check_in("statut", "statut", enums.STATUTS_RAPPROCHEMENT),
        check_in("origine", "origine", enums.ORIGINES_OPERATION),
        CheckConstraint("debit >= 0", name="debit_positif"),
        CheckConstraint("credit >= 0", name="credit_positif"),
        CheckConstraint("montant = credit - debit", name="montant_coherent"),
        Index("ix_bank_transactions_compte_date", "bank_account_id", "date_operation"),
        Index("ix_bank_transactions_date_montant", "date_operation", "montant"),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    statement_id: Mapped[int] = mapped_column(ForeignKey("bank_statements.id"), index=True)
    bank_account_id: Mapped[int] = mapped_column(ForeignKey("bank_accounts.id"))
    pointage_type_id: Mapped[int | None] = mapped_column(ForeignKey("pointage_types.id"))
    date_operation: Mapped[date] = mapped_column(Date)
    date_valeur: Mapped[date | None] = mapped_column(Date)
    libelle: Mapped[str] = mapped_column(Text)
    reference: Mapped[str | None] = mapped_column(String(60), index=True)
    debit: Mapped[Montant] = mapped_column(server_default="0")
    credit: Mapped[Montant] = mapped_column(server_default="0")
    montant: Mapped[Montant]
    solde: Mapped[Montant | None]
    # Champ « Lettrage / Escompte » du relevé : définition métier à confirmer, conservé en texte libre
    lettrage_escompte: Mapped[str | None] = mapped_column(String(120))
    commentaire: Mapped[str | None] = mapped_column(Text)
    hash_ligne: Mapped[str] = mapped_column(String(64))
    statut: Mapped[str] = mapped_column(
        String(20), default="Non rapprochée", server_default="Non rapprochée", index=True
    )
    # « Corrigée » : au moins un champ modifié dans l'aperçu avant l'enregistrement (tracé dans l'audit)
    origine: Mapped[str] = mapped_column(String(10), default="Fichier", server_default="Fichier")
    # Solde calculé par SIMTIS (solde précédent − débit + crédit) : le fichier n'avait pas de soldes
    solde_calcule: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Rang chronologique dans son relevé (08/10/2026) : un fichier du plus récent au plus ancien est
    # importé dans son ordre, l'id ne dit donc pas quelle opération est la dernière du jour
    ordre: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    statement: Mapped[BankStatement] = relationship()
    pointage_type: Mapped[PointageType | None] = relationship()


class AccountingEntry(TimestampMixin, Base):
    """Écriture comptable importée de Sage / SI. Elle n'est jamais créée ni modifiée dans SIMTIS."""

    __tablename__ = "accounting_entries"
    __table_args__ = (
        UniqueConstraint("company_id", "hash_ligne", name="uq_accounting_entries_societe_hash"),
        check_in("statut", "statut", enums.STATUTS_RAPPROCHEMENT),
        CheckConstraint("debit >= 0", name="debit_positif"),
        CheckConstraint("credit >= 0", name="credit_positif"),
        CheckConstraint("montant = credit - debit", name="montant_coherent"),
        Index("ix_accounting_entries_societe_date", "company_id", "date_ecriture"),
        Index("ix_accounting_entries_date_montant", "date_ecriture", "montant"),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batches.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    bank_account_id: Mapped[int | None] = mapped_column(ForeignKey("bank_accounts.id"))
    journal: Mapped[str | None] = mapped_column(String(20))
    compte: Mapped[str | None] = mapped_column(String(20))
    date_ecriture: Mapped[date] = mapped_column(Date)
    libelle: Mapped[str] = mapped_column(Text)
    reference: Mapped[str | None] = mapped_column(String(60), index=True)
    debit: Mapped[Montant] = mapped_column(server_default="0")
    credit: Mapped[Montant] = mapped_column(server_default="0")
    montant: Mapped[Montant]
    numero_piece: Mapped[str | None] = mapped_column(String(60), index=True)
    echeance: Mapped[date | None] = mapped_column(Date)
    tiers: Mapped[str | None] = mapped_column(String(120))
    hash_ligne: Mapped[str] = mapped_column(String(64))
    statut: Mapped[str] = mapped_column(
        String(20), default="Non rapprochée", server_default="Non rapprochée", index=True
    )

    company: Mapped[Company] = relationship()
