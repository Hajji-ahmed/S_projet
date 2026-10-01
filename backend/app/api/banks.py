from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.deps import client_ip, require_permission
from app.core.db import get_db
from app.core.permissions import PermissionCode
from app.schemas.bank import BankCreate, BankOut, BankStatusUpdate, BankUpdate
from app.services import bank_service
from app.services.auth_service import CurrentUser

router = APIRouter(prefix="/banks", tags=["banks"])

can_view = require_permission(PermissionCode.POSITION_VIEW)
can_manage = require_permission(PermissionCode.BANKS_MANAGE)


@router.get("", response_model=list[BankOut])
def list_banks(
    company_id: int | None = None,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_view),
) -> list[BankOut]:
    """Avec `company_id`, `nb_comptes_actifs` ne compte que les comptes de cette société."""
    return [BankOut.from_summary(summary) for summary in bank_service.list_banks(db, company_id)]


@router.get("/{bank_id}", response_model=BankOut)
def get_bank(
    bank_id: int, db: Session = Depends(get_db), _user: CurrentUser = Depends(can_view)
) -> BankOut:
    return BankOut.from_summary(bank_service.get_bank(db, bank_id))


@router.post("", response_model=BankOut, status_code=status.HTTP_201_CREATED)
def create_bank(
    body: BankCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_manage),
) -> BankOut:
    summary = bank_service.create_bank(
        db,
        code=body.code,
        nom=body.nom,
        logo=body.logo,
        ordre_affichage=body.ordre_affichage,
        acteur_id=user.id,
        ip=client_ip(request),
    )
    return BankOut.from_summary(summary)


@router.put("/{bank_id}", response_model=BankOut)
def update_bank(
    bank_id: int,
    body: BankUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_manage),
) -> BankOut:
    summary = bank_service.update_bank(
        db,
        bank_id,
        nom=body.nom,
        logo=body.logo,
        ordre_affichage=body.ordre_affichage,
        acteur_id=user.id,
        ip=client_ip(request),
    )
    return BankOut.from_summary(summary)


@router.patch("/{bank_id}/status", response_model=BankOut)
def set_bank_status(
    bank_id: int,
    body: BankStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_manage),
) -> BankOut:
    summary = bank_service.set_bank_status(
        db, bank_id, actif=body.actif, acteur_id=user.id, ip=client_ip(request)
    )
    return BankOut.from_summary(summary)
