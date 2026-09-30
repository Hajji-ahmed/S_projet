"""Prévisions de trésorerie."""

from datetime import date

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import enums
from app.models.base import Base, Montant, TimestampMixin, check_in


class ForecastCategory(TimestampMixin, Base):
    """Catégorie de flux prévisionnel (Encaissement, Escompte, Douane, Paie, Refinancement, Chèques, Autre).

    `sens_par_defaut` n'est renseigné que lorsque le sens est certain : Escompte, Refinancement, Chèques
    et Autre restent à NULL tant que le métier ne les a pas tranchés. Le sens réel est porté par chaque prévision.
    """

    __tablename__ = "forecast_categories"
    __table_args__ = (
        CheckConstraint(
            "sens_par_defaut IS NULL OR sens_par_defaut IN ('Entrée', 'Sortie')",
            name="sens_par_defaut",
        ),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    libelle: Mapped[str] = mapped_column(String(80))
    sens_par_defaut: Mapped[str | None] = mapped_column(String(6))


class CashForecast(TimestampMixin, Base):
    """Flux de trésorerie prévu.

    Une prévision sans `bank_id` est un montant de la journée (cellules Encaissement / Escompte / Douane du
    tableau Prévisions). Avec `bank_id`, elle concerne une banque précise (colonnes de banques du tableau).
    """

    __tablename__ = "cash_forecasts"
    __table_args__ = (
        check_in("sens", "sens", enums.SENS),
        check_in("statut", "statut", enums.STATUTS_PREVISION),
        CheckConstraint("montant > 0", name="montant_positif"),
        CheckConstraint(
            "statut <> 'Réalisé' OR date_realisation IS NOT NULL", name="realisation_datee"
        ),
        Index("ix_cash_forecasts_societe_date", "company_id", "date_prevue"),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    bank_id: Mapped[int | None] = mapped_column(ForeignKey("banks.id"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("forecast_categories.id"), index=True)
    sens: Mapped[str] = mapped_column(String(6))
    libelle: Mapped[str | None] = mapped_column(String(160))
    date_prevue: Mapped[date] = mapped_column(Date)
    montant: Mapped[Montant]
    devise: Mapped[str] = mapped_column(ForeignKey("currencies.code"), default="MAD")
    statut: Mapped[str] = mapped_column(
        String(10), default="Prévu", server_default="Prévu", index=True
    )
    date_realisation: Mapped[date | None] = mapped_column(Date)
    bank_transaction_id: Mapped[int | None] = mapped_column(ForeignKey("bank_transactions.id"))
    commentaire: Mapped[str | None] = mapped_column(Text)

    category: Mapped[ForecastCategory] = relationship()
