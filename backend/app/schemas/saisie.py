"""Tableaux Devises et Prévisions saisis à la main : une grille par société et par date.

Les montants circulent en texte exact (« 1250.50 ») ; une cellule vide vaut `null`, jamais 0.
"""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import SaisieDevise, SaisiePrevision, SaisiePrevisionJour, enums
from app.services.saisie_service import DeviseCell, PrevisionCell

# Montant d'une cellule : positif ou négatif, 2 décimales au plus
Montant = Annotated[Decimal, Field(max_digits=18, decimal_places=2)]
LigneDevise = Literal["EUR", "USD", "Exp DH convertible"]
NumeroLigne = Annotated[int, Field(ge=1, le=enums.NB_LIGNES_PREVISIONS)]


class MontantBanque(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bank_id: int
    montant: Montant


def _unique(values: list, message: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(message)


# --- Devises ---------------------------------------------------------------------------------------


class LigneDevisesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ligne: LigneDevise
    banques: list[MontantBanque] = Field(default_factory=list, max_length=50)
    total: Montant | None = None
    depassement: Montant | None = None

    @model_validator(mode="after")
    def _une_valeur_par_banque(self) -> "LigneDevisesIn":
        _unique([item.bank_id for item in self.banques], "Une banque apparaît deux fois.")
        return self


class DevisesIn(BaseModel):
    """La grille complète de la date : une cellule absente est vidée."""

    model_config = ConfigDict(extra="forbid")

    lignes: list[LigneDevisesIn] = Field(max_length=len(enums.LIGNES_DEVISES))

    @model_validator(mode="after")
    def _lignes_uniques(self) -> "DevisesIn":
        _unique([item.ligne for item in self.lignes], "Une ligne apparaît deux fois.")
        return self

    def cells(self) -> dict[DeviseCell, Decimal | None]:
        cells: dict[DeviseCell, Decimal | None] = {}
        for item in self.lignes:
            cells[(item.ligne, "TOTAL", None)] = item.total
            cells[(item.ligne, "DEPASSEMENT", None)] = item.depassement
            for cell in item.banques:
                cells[(item.ligne, "Banque", cell.bank_id)] = cell.montant
        return cells


class LigneDevisesOut(BaseModel):
    ligne: str
    banques: list[MontantBanque]
    total: Decimal | None
    depassement: Decimal | None


class DevisesOut(BaseModel):
    company_id: int
    jour: date
    lignes: list[LigneDevisesOut]

    @classmethod
    def from_rows(cls, company_id: int, jour: date, rows: list[SaisieDevise]) -> "DevisesOut":
        """Toujours les trois lignes, dans l'ordre du classeur."""
        lignes = []
        for ligne in enums.LIGNES_DEVISES:
            mine = [row for row in rows if row.ligne == ligne]
            extra = {row.colonne: row.montant for row in mine if row.bank_id is None}
            lignes.append(
                LigneDevisesOut(
                    ligne=ligne,
                    banques=[
                        MontantBanque(bank_id=row.bank_id, montant=row.montant)
                        for row in mine
                        if row.bank_id is not None
                    ],
                    total=extra.get("TOTAL"),
                    depassement=extra.get("DEPASSEMENT"),
                )
            )
        return cls(company_id=company_id, jour=jour, lignes=lignes)


# --- Prévisions ------------------------------------------------------------------------------------


class LignePrevisionsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ligne: NumeroLigne
    libelle: str | None = Field(default=None, max_length=80)
    banques: list[MontantBanque] = Field(default_factory=list, max_length=50)
    # Une valeur par ligne depuis le 03/10/2026 (avant : une pour toute la journée)
    encaissement: Montant | None = None
    escompte: Montant | None = None
    douane: Montant | None = None

    @model_validator(mode="after")
    def _une_valeur_par_banque(self) -> "LignePrevisionsIn":
        _unique([item.bank_id for item in self.banques], "Une banque apparaît deux fois.")
        return self


class PrevisionsIn(BaseModel):
    """La grille complète de la date : une cellule absente est vidée."""

    model_config = ConfigDict(extra="forbid")

    lignes: list[LignePrevisionsIn] = Field(max_length=enums.NB_LIGNES_PREVISIONS)

    @model_validator(mode="after")
    def _lignes_uniques(self) -> "PrevisionsIn":
        _unique([item.ligne for item in self.lignes], "Une ligne apparaît deux fois.")
        return self

    def cells(self) -> dict[PrevisionCell, str | Decimal | None]:
        cells: dict[PrevisionCell, str | Decimal | None] = {}
        for item in self.lignes:
            cells[(item.ligne, None)] = item.libelle
            for cell in item.banques:
                cells[(item.ligne, cell.bank_id)] = cell.montant
        return cells

    def jour_values(self) -> dict[int, dict[str, Decimal | None]]:
        """Encaissement, Escompte et Douane de chaque ligne envoyée."""
        return {
            item.ligne: {
                "encaissement": item.encaissement,
                "escompte": item.escompte,
                "douane": item.douane,
            }
            for item in self.lignes
        }


class LignePrevisionsOut(BaseModel):
    ligne: int
    libelle: str | None
    banques: list[MontantBanque]
    encaissement: Decimal | None
    escompte: Decimal | None
    douane: Decimal | None


class PrevisionsOut(BaseModel):
    company_id: int
    jour: date
    lignes: list[LignePrevisionsOut]

    @classmethod
    def from_rows(
        cls,
        company_id: int,
        jour: date,
        rows: list[SaisiePrevision],
        days: list[SaisiePrevisionJour],
    ) -> "PrevisionsOut":
        """Toujours les 14 lignes du bloc, même vides."""
        by_line = {day.ligne: day for day in days}
        lignes = []
        for numero in range(1, enums.NB_LIGNES_PREVISIONS + 1):
            mine = [row for row in rows if row.ligne == numero]
            day = by_line.get(numero)
            lignes.append(
                LignePrevisionsOut(
                    ligne=numero,
                    libelle=next((row.libelle for row in mine if row.bank_id is None), None),
                    banques=[
                        MontantBanque(bank_id=row.bank_id, montant=row.montant)
                        for row in mine
                        if row.bank_id is not None
                    ],
                    encaissement=day.encaissement if day else None,
                    escompte=day.escompte if day else None,
                    douane=day.douane if day else None,
                )
            )
        return cls(company_id=company_id, jour=jour, lignes=lignes)
