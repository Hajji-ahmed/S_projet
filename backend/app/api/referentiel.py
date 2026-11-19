"""Listes de référence utiles à tous les écrans : sociétés, devises et types de pointage (tout
utilisateur connecté). La gestion des sociétés (création, renommage, activation) exige
`admin.settings` (17/11/2026)."""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_user, require_permission
from app.core.db import get_db
from app.core.permissions import PermissionCode
from app.models import Company
from app.schemas.account import (
    CompanyAdminOut,
    CompanyCreate,
    CompanyOut,
    CompanyUpdate,
    CurrencyOut,
)
from app.schemas.statement import PointageTypeOut
from app.services import account_service, import_service, societe_service
from app.services.auth_service import CurrentUser

router = APIRouter(tags=["referentiel"])

can_manage_companies = require_permission(PermissionCode.ADMIN_SETTINGS)


def _admin_out(company: Company) -> CompanyAdminOut:
    return CompanyAdminOut(id=company.id, code=company.code, nom=company.nom, actif=company.actif)


@router.get("/companies", response_model=list[CompanyOut])
def list_companies(
    db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
) -> list[CompanyOut]:
    """Sociétés actives que la personne peut voir (sélecteur du header, 19/11/2026)."""
    return [
        CompanyOut(id=company.id, code=company.code, nom=company.nom)
        for company in account_service.list_companies(db)
        if user.peut_voir(company.id)
    ]


@router.get("/companies/toutes", response_model=list[CompanyAdminOut])
def list_all_companies(
    db: Session = Depends(get_db), _user: CurrentUser = Depends(can_manage_companies)
) -> list[CompanyAdminOut]:
    return [_admin_out(company) for company in societe_service.list_all(db)]


@router.post("/companies", response_model=CompanyAdminOut, status_code=status.HTTP_201_CREATED)
def create_company(
    body: CompanyCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_manage_companies),
) -> CompanyAdminOut:
    company = societe_service.create(
        db, code=body.code, nom=body.nom, acteur_id=user.id, ip=client_ip(request)
    )
    return _admin_out(company)


@router.patch("/companies/{company_id}", response_model=CompanyAdminOut)
def update_company(
    company_id: int,
    body: CompanyUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_manage_companies),
) -> CompanyAdminOut:
    company = societe_service.update(
        db,
        company_id,
        nom=body.nom,
        actif=body.actif,
        acteur_id=user.id,
        ip=client_ip(request),
    )
    return _admin_out(company)


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
