import re
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import BankAccount
from app.services.account_service import fraction_to_pct, normalize_numero

NUMERO_PATTERN = re.compile(r"^[A-Z0-9-]{5,40}$")
COMPTE_COMPTABLE_PATTERN = re.compile(r"^[A-Z0-9]{1,20}$")

TypeCompte = Literal["Courant", "DH convertible"]
# LIGNE : montant exact, 2 décimales au plus. Envoyé en texte ("500000.00") pour ne rien perdre.
Ligne = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=2)]
# Taux saisi en pourcentage (4.5 = 4,5 %), 4 décimales au plus
TauxPct = Annotated[Decimal, Field(ge=0, le=100, max_digits=7, decimal_places=4)]


class CompanyOut(BaseModel):
    id: int
    code: str
    nom: str


class CurrencyOut(BaseModel):
    code: str
    libelle: str


class AccountOut(BaseModel):
    id: int
    company_id: int
    bank_id: int
    bank_code: str
    bank_nom: str
    bank_logo: str | None
    libelle: str
    numero: str
    devise: str
    type_compte: TypeCompte
    compte_comptable: str | None
    credit_autorise: Decimal
    taux_interet_pct: Decimal | None
    actif: bool

    @classmethod
    def from_model(cls, account: BankAccount) -> "AccountOut":
        return cls(
            id=account.id,
            company_id=account.company_id,
            bank_id=account.bank_id,
            bank_code=account.bank.code,
            bank_nom=account.bank.nom,
            bank_logo=account.bank.logo,
            libelle=account.libelle,
            numero=account.numero,
            devise=account.devise,
            type_compte=account.type_compte,
            compte_comptable=account.compte_comptable,
            credit_autorise=account.credit_autorise,
            taux_interet_pct=fraction_to_pct(account.taux_interet),
            actif=account.actif,
        )


def _clean_libelle(value: str) -> str:
    value = value.strip()
    if not 2 <= len(value) <= 120:
        raise ValueError("Le libellé doit contenir entre 2 et 120 caractères.")
    return value


def _clean_numero(value: str) -> str:
    value = normalize_numero(value)
    if not NUMERO_PATTERN.match(value):
        raise ValueError("Le numéro doit contenir 5 à 40 lettres, chiffres ou tirets.")
    return value


def _clean_compte_comptable(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    value = value.strip().upper()
    if not COMPTE_COMPTABLE_PATTERN.match(value):
        raise ValueError("Le compte comptable contient 1 à 20 lettres ou chiffres (ex. 5141).")
    return value


class AccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_id: int
    bank_id: int
    libelle: str
    numero: str
    devise: str = Field(pattern=r"^[A-Za-z]{3}$")
    type_compte: TypeCompte = "Courant"
    compte_comptable: str | None = None
    credit_autorise: Ligne
    taux_interet_pct: TauxPct | None = None

    _libelle = field_validator("libelle")(_clean_libelle)
    _numero = field_validator("numero")(_clean_numero)
    _compte = field_validator("compte_comptable")(_clean_compte_comptable)

    @field_validator("devise")
    @classmethod
    def _devise(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def _dh_convertible_en_mad(self) -> "AccountCreate":
        if self.type_compte == "DH convertible" and self.devise != "MAD":
            raise ValueError("Un compte DH convertible doit être en MAD.")
        return self


class AccountUpdate(BaseModel):
    """Société, banque et devise n'en font pas partie : elles ne changent plus après la création."""

    model_config = ConfigDict(extra="forbid")

    libelle: str
    numero: str
    type_compte: TypeCompte
    compte_comptable: str | None
    credit_autorise: Ligne
    taux_interet_pct: TauxPct | None = None

    _libelle = field_validator("libelle")(_clean_libelle)
    _numero = field_validator("numero")(_clean_numero)
    _compte = field_validator("compte_comptable")(_clean_compte_comptable)


class AccountStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actif: bool
