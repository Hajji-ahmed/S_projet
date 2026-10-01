"""Listes de référence utiles à tous les écrans : sociétés et devises (tout utilisateur connecté)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.account import CompanyOut, CurrencyOut
from app.services import account_service

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
