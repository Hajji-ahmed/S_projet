import re
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import BankAccount
from app.schemas.balance import FiguresOut
from app.services.account_service import fraction_to_pct, normalize_numero
from app.services.position_service import AccountFigures

NUMERO_PATTERN = re.compile(r"^[A-Z0-9-]{5,40}$")
COMPTE_COMPTABLE_PATTERN = re.compile(r"^[A-Z0-9]{1,20}$")
COMPTES_COMPTABLES_MAX = 9  # 9 × 20 + 8 virgules = 188 ≤ 200 caractères en base
JOURNAL_SAGE_PATTERN = re.compile(r"^[A-Z0-9]{1,10}$")

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
    journal_sage: str | None
    # Comptabilisation des droits de timbre (13/10/2026)
    journal_frais: str | None = None
    compte_timbre: str | None = None
    compte_commission: str | None = None
    compte_commission_effet: str | None = None
    compte_tva: str | None = None
    credit_autorise: Decimal
    taux_interet_pct: Decimal | None
    actif: bool
    # Vrai si le compte a des relevés, opérations, écritures, imports ou contrôles : il ne peut alors
    # être que désactivé, jamais effacé
    a_historique: bool = False
    # Chiffres à aujourd'hui (solde, crédit et position disponibles), calculés à partir des soldes saisis
    figures: FiguresOut | None = None

    @classmethod
    def from_model(
        cls,
        account: BankAccount,
        figures: AccountFigures | None = None,
        a_historique: bool = False,
    ) -> "AccountOut":
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
            journal_sage=account.journal_sage,
            journal_frais=account.journal_frais,
            compte_timbre=account.compte_timbre,
            compte_commission=account.compte_commission,
            compte_commission_effet=account.compte_commission_effet,
            compte_tva=account.compte_tva,
            credit_autorise=account.credit_autorise,
            taux_interet_pct=fraction_to_pct(account.taux_interet),
            actif=account.actif,
            a_historique=a_historique,
            figures=FiguresOut.from_figures(figures) if figures else None,
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
    """Un ou plusieurs comptes, séparés par des virgules, des points-virgules ou des espaces
    (« 51410000, 51410100 » → « 51410000,51410100 », 27/10/2026). Chacun : 1 à 20 lettres ou
    chiffres ; un compte répété n'est gardé qu'une fois."""
    if value is None or not value.strip():
        return None
    comptes: list[str] = []
    for item in re.split(r"[,;\s]+", value.strip().upper()):
        if not item:
            continue
        if not COMPTE_COMPTABLE_PATTERN.match(item):
            raise ValueError(
                "Chaque compte comptable contient 1 à 20 lettres ou chiffres, séparés par des "
                "virgules (ex. 51410000, 51410100)."
            )
        if item not in comptes:
            comptes.append(item)
    if len(comptes) > COMPTES_COMPTABLES_MAX:
        raise ValueError(f"{COMPTES_COMPTABLES_MAX} comptes comptables au plus.")
    return ",".join(comptes) or None


def _clean_journal_sage(value: str | None) -> str | None:
    """Un ou plusieurs journaux, séparés par des virgules, des points-virgules ou des espaces
    (« 5243, 5543 » → « 5243,5543 », 12/10/2026). Chacun : 1 à 10 lettres ou chiffres."""
    if value is None or not value.strip():
        return None
    journaux: list[str] = []
    for item in re.split(r"[,;\s]+", value.strip().upper()):
        if not item:
            continue
        if not JOURNAL_SAGE_PATTERN.match(item):
            raise ValueError(
                "Chaque journal Sage contient 1 à 10 lettres ou chiffres, séparés par des "
                "virgules (ex. 5243, 5543)."
            )
        if item not in journaux:
            journaux.append(item)
    texte = ",".join(journaux)
    if len(texte) > 120:
        raise ValueError("Trop de journaux Sage pour un compte.")
    return texte or None


def _clean_journal_frais(value: str | None) -> str | None:
    """Journal Sage des frais bancaires : un seul journal (ex. 5543)."""
    if value is None or not value.strip():
        return None
    value = value.strip().upper()
    if not JOURNAL_SAGE_PATTERN.match(value):
        raise ValueError("Le journal des frais contient 1 à 10 lettres ou chiffres (ex. 5543).")
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
    journal_sage: str | None = None
    journal_frais: str | None = None
    compte_timbre: str | None = None
    compte_commission: str | None = None
    compte_commission_effet: str | None = None
    compte_tva: str | None = None
    credit_autorise: Ligne
    taux_interet_pct: TauxPct | None = None

    _libelle = field_validator("libelle")(_clean_libelle)
    _numero = field_validator("numero")(_clean_numero)
    _compte = field_validator(
        "compte_comptable",
        "compte_timbre",
        "compte_commission",
        "compte_commission_effet",
        "compte_tva",
    )(_clean_compte_comptable)
    _journal = field_validator("journal_sage")(_clean_journal_sage)
    _journal_frais = field_validator("journal_frais")(_clean_journal_frais)

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
    journal_sage: str | None
    journal_frais: str | None = None
    compte_timbre: str | None = None
    compte_commission: str | None = None
    compte_commission_effet: str | None = None
    compte_tva: str | None = None
    credit_autorise: Ligne
    taux_interet_pct: TauxPct | None = None

    _libelle = field_validator("libelle")(_clean_libelle)
    _numero = field_validator("numero")(_clean_numero)
    _compte = field_validator(
        "compte_comptable",
        "compte_timbre",
        "compte_commission",
        "compte_commission_effet",
        "compte_tva",
    )(_clean_compte_comptable)
    _journal = field_validator("journal_sage")(_clean_journal_sage)
    _journal_frais = field_validator("journal_frais")(_clean_journal_frais)


class AccountStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actif: bool
