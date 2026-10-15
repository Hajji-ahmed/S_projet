"""Paramètres (P16.3)."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models import ColumnMapping, ReconciliationRule
from app.services.parametres_service import GENRES


class RegleOut(BaseModel):
    id: int
    code: str
    libelle: str
    # critere (points + actif ; DATE a aussi une tolérance en jours), seuil (points), fenetre (jours)
    genre: str
    poids: Decimal
    tolerance: Decimal | None
    actif: bool
    updated_at: datetime

    @classmethod
    def of(cls, rule: ReconciliationRule) -> "RegleOut":
        return cls(
            id=rule.id,
            code=rule.code,
            libelle=rule.libelle,
            genre=GENRES.get(rule.code, "autre"),
            poids=rule.poids,
            tolerance=rule.tolerance,
            actif=rule.actif,
            updated_at=rule.updated_at,
        )


class RegleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    poids: Decimal
    tolerance: Decimal | None = None
    actif: bool = True


class GrilleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    regles: list[RegleIn]


class MappingOut(BaseModel):
    id: int
    type: str
    nom: str
    banque: str | None
    company_id: int | None
    # Champ standard → colonne du fichier
    mapping: dict
    updated_at: datetime

    @classmethod
    def of(cls, mapping: ColumnMapping) -> "MappingOut":
        return cls(
            id=mapping.id,
            type=mapping.type,
            nom=mapping.nom,
            banque=mapping.bank.code if mapping.bank else None,
            company_id=mapping.company_id,
            mapping=mapping.mapping,
            updated_at=mapping.updated_at,
        )
