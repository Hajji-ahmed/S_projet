import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.bank_service import MAX_DISPLAY_ORDER, BankSummary

CODE_PATTERN = re.compile(r"^[A-Z0-9]{2,10}$")
# Logo : un fichier fourni dans frontend/public/banques/, jamais une adresse externe
LOGO_PATTERN = re.compile(r"^/banques/[a-z0-9][a-z0-9_-]*\.(png|jpg|jpeg|webp|svg)$")


def _clean_nom(value: str) -> str:
    value = value.strip()
    if not 2 <= len(value) <= 120:
        raise ValueError("Le nom doit contenir entre 2 et 120 caractères.")
    return value


def _clean_logo(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    value = value.strip()
    if not LOGO_PATTERN.match(value):
        raise ValueError("Logo invalide : choisissez un fichier du dossier /banques/.")
    return value


class BankOut(BaseModel):
    id: int
    code: str
    nom: str
    logo: str | None
    ordre_affichage: int
    actif: bool
    nb_comptes_actifs: int

    @classmethod
    def from_summary(cls, summary: BankSummary) -> "BankOut":
        bank = summary.bank
        return cls(
            id=bank.id,
            code=bank.code,
            nom=bank.nom,
            logo=bank.logo,
            ordre_affichage=bank.ordre_affichage,
            actif=bank.actif,
            nb_comptes_actifs=summary.nb_comptes_actifs,
        )


class BankCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    nom: str
    logo: str | None = None
    ordre_affichage: int | None = Field(default=None, ge=0, le=MAX_DISPLAY_ORDER)

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        value = value.strip().upper()
        if not CODE_PATTERN.match(value):
            raise ValueError("Le code doit contenir 2 à 10 lettres ou chiffres (ex. AWB).")
        return value

    _nom = field_validator("nom")(_clean_nom)
    _logo = field_validator("logo")(_clean_logo)


class BankUpdate(BaseModel):
    """Le code n'en fait pas partie : il n'est plus modifiable après la création."""

    model_config = ConfigDict(extra="forbid")

    nom: str
    logo: str | None
    ordre_affichage: int = Field(ge=0, le=MAX_DISPLAY_ORDER)

    _nom = field_validator("nom")(_clean_nom)
    _logo = field_validator("logo")(_clean_logo)


class BankStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actif: bool
