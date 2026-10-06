"""Référentiel : sociétés, banques, devises, types de pointage, comptes, soldes journaliers, taux."""

from datetime import date
from decimal import Decimal

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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import enums
from app.models.base import Base, Montant, Taux, TimestampMixin, check_in


class Company(TimestampMixin, Base):
    """Société du groupe (Simtis, Tefil). Les positions ne sont jamais consolidées entre sociétés."""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    nom: Mapped[str] = mapped_column(String(120))
    actif: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Bank(TimestampMixin, Base):
    """Banque. Les tableaux l'affichent par son `code` (AWB, BMCE, BP, CIH, BMCI)."""

    __tablename__ = "banks"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    nom: Mapped[str] = mapped_column(String(120))
    logo: Mapped[str | None] = mapped_column(String(255))
    ordre_affichage: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    actif: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Currency(Base):
    __tablename__ = "currencies"

    code: Mapped[str] = mapped_column(String(3), primary_key=True)
    libelle: Mapped[str] = mapped_column(String(60))


class PointageType(TimestampMixin, Base):
    """Type d'opération du champ « Pointage » des relevés (encaissement, décaissement, frais...)."""

    __tablename__ = "pointage_types"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    libelle: Mapped[str] = mapped_column(String(80))
    actif: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class BankAccount(TimestampMixin, Base):
    """Compte bancaire d'une société.

    `credit_autorise` est la « LIGNE » du tableau Banques. Le solde et le crédit utilisé évoluent chaque
    jour : ils vivent dans `BankAccountBalance`, pas ici. Crédit disponible, Disponible Fc reel et
    Dépassement sont calculés par les services, jamais enregistrés.
    """

    __tablename__ = "bank_accounts"
    __table_args__ = (
        check_in("type_compte", "type_compte", enums.TYPES_COMPTE),
        CheckConstraint("credit_autorise >= 0", name="credit_autorise_positif"),
        CheckConstraint(
            "type_compte <> 'DH convertible' OR devise = 'MAD'", name="dh_convertible_en_mad"
        ),
        # Une seule cellule par banque dans les tableaux du classeur : pour une société, une banque a au
        # plus UN compte actif par devise et par type. Un compte désactivé libère la place (nouveau RIB).
        Index(
            "uq_bank_accounts_compte_actif_par_banque",
            "company_id",
            "bank_id",
            "devise",
            "type_compte",
            unique=True,
            postgresql_where=text("actif"),
        ),
        # Un journal Sage ne sert qu'à un compte actif par société (P10, migration 0010)
        Index(
            "uq_bank_accounts_journal_sage_actif",
            "company_id",
            "journal_sage",
            unique=True,
            postgresql_where=text("journal_sage IS NOT NULL AND actif"),
        ),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    bank_id: Mapped[int] = mapped_column(ForeignKey("banks.id"), index=True)
    libelle: Mapped[str] = mapped_column(String(120))
    numero: Mapped[str] = mapped_column(String(40), unique=True)
    devise: Mapped[str] = mapped_column(ForeignKey("currencies.code"), default="MAD")
    type_compte: Mapped[str] = mapped_column(
        String(20), default="Courant", server_default="Courant"
    )
    # Compte du plan comptable Sage lié à ce compte bancaire (ex. 5141), utilisé en P10
    compte_comptable: Mapped[str | None] = mapped_column(String(20))
    # Code du journal de banque dans Sage (ex. BQ1) : rattache les écritures importées (P10)
    journal_sage: Mapped[str | None] = mapped_column(String(10))
    credit_autorise: Mapped[Montant] = mapped_column(default=Decimal("0"), server_default="0")
    taux_interet: Mapped[Taux | None]
    actif: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    company: Mapped[Company] = relationship()
    bank: Mapped[Bank] = relationship()


class BankAccountBalance(TimestampMixin, Base):
    """Solde et crédit utilisé d'un compte à une date : alimente les lignes « facilité de caisse »."""

    __tablename__ = "bank_account_balances"
    __table_args__ = (
        UniqueConstraint(
            "bank_account_id", "date_solde", name="uq_bank_account_balances_compte_date"
        ),
        check_in("source", "source", enums.SOURCES_SOLDE),
        CheckConstraint(
            "solde IS NOT NULL OR credit_utilise IS NOT NULL", name="un_montant_renseigne"
        ),
        CheckConstraint("credit_utilise >= 0", name="credit_utilise_positif"),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    bank_account_id: Mapped[int] = mapped_column(ForeignKey("bank_accounts.id"), index=True)
    date_solde: Mapped[date] = mapped_column(Date)
    solde: Mapped[Montant | None]
    credit_utilise: Mapped[Montant | None]
    source: Mapped[str] = mapped_column(String(10), default="Saisie", server_default="Saisie")
    # Renseigné par l'authentification (P5) : la clé étrangère vers `users` est ajoutée avec `securite.py`
    saisi_par_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    commentaire: Mapped[str | None] = mapped_column(Text)

    bank_account: Mapped[BankAccount] = relationship()


class ExchangeRate(TimestampMixin, Base):
    """Taux de change saisi à la main. Toute conversion en MAD conserve le taux et sa date."""

    __tablename__ = "exchange_rates"
    __table_args__ = (
        UniqueConstraint("devise", "date_taux", name="uq_exchange_rates_devise_date"),
        CheckConstraint("taux > 0", name="taux_positif"),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    devise: Mapped[str] = mapped_column(ForeignKey("currencies.code"))
    taux: Mapped[Taux]
    date_taux: Mapped[date] = mapped_column(Date)
    source: Mapped[str | None] = mapped_column(String(60))
    saisi_par_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
