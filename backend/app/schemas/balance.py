from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import BankAccountBalance
from app.services.position_service import AccountFigures

# Solde : peut être négatif (découvert). Crédit utilisé : jamais négatif. 2 décimales au plus.
Solde = Annotated[Decimal, Field(max_digits=18, decimal_places=2)]
CreditUtilise = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=2)]


class FiguresOut(BaseModel):
    """Chiffres d'un compte à aujourd'hui. `null` = inconnu (jamais saisi), jamais remplacé par 0."""

    solde: Decimal | None
    credit_utilise: Decimal | None
    credit_disponible: Decimal | None
    position_disponible: Decimal | None
    date_maj: date | None

    @classmethod
    def from_figures(cls, figures: AccountFigures) -> "FiguresOut":
        return cls(
            solde=figures.solde,
            credit_utilise=figures.credit_utilise,
            credit_disponible=figures.credit_disponible,
            position_disponible=figures.position_disponible,
            date_maj=figures.date_maj,
        )


class BalanceOut(BaseModel):
    id: int
    date_solde: date
    solde: Decimal | None
    credit_utilise: Decimal | None
    source: str
    commentaire: str | None
    saisi_par: str | None

    @classmethod
    def from_row(cls, balance: BankAccountBalance, saisi_par: str | None) -> "BalanceOut":
        return cls(
            id=balance.id,
            date_solde=balance.date_solde,
            solde=balance.solde,
            credit_utilise=balance.credit_utilise,
            source=balance.source,
            commentaire=balance.commentaire,
            saisi_par=saisi_par,
        )


class BalanceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    solde: Solde | None = None
    credit_utilise: CreditUtilise | None = None
    commentaire: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _au_moins_un_montant(self) -> "BalanceIn":
        if self.solde is None and self.credit_utilise is None:
            raise ValueError("Saisissez le solde, le crédit utilisé, ou les deux.")
        return self
