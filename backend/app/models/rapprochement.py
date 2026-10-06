"""Rapprochement bancaire, contrôles de solde et écarts."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import enums
from app.models.base import Base, Montant, TimestampMixin, check_in


class ReconciliationRule(TimestampMixin, Base):
    """Critère de la grille de score du rapprochement. Vide tant que la grille n'est pas validée."""

    __tablename__ = "reconciliation_rules"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    libelle: Mapped[str] = mapped_column(String(120))
    critere: Mapped[str] = mapped_column(String(40))
    poids: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    tolerance: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    actif: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class ReconciliationMatch(TimestampMixin, Base):
    """Correspondance entre des transactions bancaires et des écritures comptables (1-1, 1-N, N-1, N-N).

    Le moteur ne fait que proposer : `valide_par_id` et `valide_le` ne sont renseignés que par un humain.
    """

    __tablename__ = "reconciliation_matches"
    __table_args__ = (
        check_in("type", "type", enums.TYPES_CORRESPONDANCE),
        check_in("origine", "origine", enums.ORIGINES_CORRESPONDANCE),
        check_in("statut", "statut", enums.STATUTS_CORRESPONDANCE),
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="score_0_100"),
        CheckConstraint(
            "statut <> 'Validée' OR (valide_par_id IS NOT NULL AND valide_le IS NOT NULL)",
            name="validation_tracee",
        ),
        # Toute décision (validation, rejet, annulation) a son auteur et sa date (migration 0013)
        CheckConstraint(
            "statut = 'Proposée' OR (decide_par_id IS NOT NULL AND decide_le IS NOT NULL)",
            name="decision_tracee",
        ),
        Index("ix_reconciliation_matches_societe_decision", "company_id", "decide_le"),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    type: Mapped[str] = mapped_column(String(3))
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    statut: Mapped[str] = mapped_column(String(10), default="Proposée", server_default="Proposée")
    origine: Mapped[str] = mapped_column(String(12), default="Automatique")
    valide_par_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    valide_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Dernière décision humaine : validation, rejet ou annulation (historique, migration 0013)
    decide_par_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decide_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    commentaire: Mapped[str | None] = mapped_column(Text)
    # Points obtenus par critère au moment de la proposition : {"montant": "30.00", ...}
    detail_score: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    items: Mapped[list["ReconciliationMatchItem"]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )


class ReconciliationMatchItem(Base):
    """Un élément d'une correspondance : soit une transaction bancaire, soit une écriture comptable."""

    __tablename__ = "reconciliation_match_items"
    __table_args__ = (
        CheckConstraint(
            "(bank_transaction_id IS NOT NULL AND accounting_entry_id IS NULL) "
            "OR (bank_transaction_id IS NULL AND accounting_entry_id IS NOT NULL)",
            name="un_seul_lien",
        ),
        CheckConstraint("montant_affecte > 0", name="montant_affecte_positif"),
        # Une opération, ou une écriture, ne fait partie que d'une correspondance active (migration 0011)
        Index(
            "uq_reconciliation_match_items_transaction_active",
            "bank_transaction_id",
            unique=True,
            postgresql_where=text("actif AND bank_transaction_id IS NOT NULL"),
        ),
        Index(
            "uq_reconciliation_match_items_ecriture_active",
            "accounting_entry_id",
            unique=True,
            postgresql_where=text("actif AND accounting_entry_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("reconciliation_matches.id", ondelete="CASCADE"), index=True
    )
    bank_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("bank_transactions.id"), index=True
    )
    accounting_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounting_entries.id"), index=True
    )
    montant_affecte: Mapped[Montant]
    # Vrai tant que la correspondance est « Proposée » ou « Validée » ; faux une fois rejetée ou annulée
    actif: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    match: Mapped[ReconciliationMatch] = relationship(back_populates="items")


class BalanceCheck(TimestampMixin, Base):
    """Contrôle du solde d'un relevé par rapport au solde enregistré du compte."""

    __tablename__ = "balance_checks"
    __table_args__ = (check_in("statut", "statut", enums.STATUTS_CONTROLE_SOLDE),)

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    bank_account_id: Mapped[int] = mapped_column(ForeignKey("bank_accounts.id"), index=True)
    bank_statement_id: Mapped[int | None] = mapped_column(ForeignKey("bank_statements.id"))
    date_controle: Mapped[date] = mapped_column(Date)
    solde_releve: Mapped[Montant]
    solde_enregistre: Mapped[Montant]
    ecart: Mapped[Montant]
    statut: Mapped[str] = mapped_column(String(10))
    commentaire: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class Discrepancy(TimestampMixin, Base):
    """Écart à traiter. Cycle : À traiter → En cours → Traité → Clôturé (la clôture exige un commentaire)."""

    __tablename__ = "discrepancies"
    __table_args__ = (
        check_in("statut", "statut", enums.STATUTS_ECART),
        check_in("type", "type", enums.TYPES_ECART),
        CheckConstraint(
            "statut <> 'Clôturé' OR (commentaire IS NOT NULL AND btrim(commentaire) <> '' "
            "AND cloture_le IS NOT NULL AND cloture_par_id IS NOT NULL)",
            name="cloture_avec_commentaire",
        ),
        # Un seul écart ouvert par opération et par écriture (migration 0012)
        Index(
            "uq_discrepancies_transaction_ouvert",
            "bank_transaction_id",
            unique=True,
            postgresql_where=text("statut <> 'Clôturé' AND bank_transaction_id IS NOT NULL"),
        ),
        Index(
            "uq_discrepancies_ecriture_ouvert",
            "accounting_entry_id",
            unique=True,
            postgresql_where=text("statut <> 'Clôturé' AND accounting_entry_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    type: Mapped[str] = mapped_column(String(30))
    bank_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("bank_transactions.id"), index=True
    )
    accounting_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounting_entries.id"), index=True
    )
    montant: Mapped[Montant]
    difference: Mapped[Montant | None]
    date_ecart: Mapped[date] = mapped_column(Date)
    responsable_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    statut: Mapped[str] = mapped_column(
        String(10), default="À traiter", server_default="À traiter", index=True
    )
    commentaire: Mapped[str | None] = mapped_column(Text)
    traite_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cloture_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cloture_par_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
