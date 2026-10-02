"""Listes de référence utiles à tous les écrans : sociétés, devises et types de pointage (tout
utilisateur connecté)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.account import CompanyOut, CurrencyOut
from app.schemas.statement import PointageTypeOut
from app.services import account_service, import_service

router = APIRouter(tags=["referentiel"])


@router.get("/companies", response_model=list[CompanyOut])
def list_companies(db: Session = Depends(get_db)) -> list[CompanyOut]:
    return [
        CompanyOut(id=company.id, code=company.code, nom=company.nom)
        for company in account_service.list_companies(db)
    ]


@router.get("/currencies", response_model=list[CurrencyOut])
def list_currencies(db: Session = Depends(get_db)) -> list[CurrencyOut]:
    return [
        CurrencyOut(code=currency.code, libelle=currency.libelle)
        for currency in account_service.list_currencies(db)
    ]


@router.get("/pointage-types", response_model=list[PointageTypeOut])
def list_pointage_types(db: Session = Depends(get_db)) -> list[PointageTypeOut]:
    """Types d'opération (Pointage) actifs, par libellé."""
    return [PointageTypeOut.model_validate(item) for item in import_service.list_pointage_types(db)]
