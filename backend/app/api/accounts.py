from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import client_ip, require_permission
from app.core.db import get_db
from app.core.permissions import PermissionCode
from app.schemas.account import AccountCreate, AccountOut, AccountStatusUpdate, AccountUpdate
from app.services import account_service
from app.services.auth_service import CurrentUser

router = APIRouter(prefix="/accounts", tags=["accounts"])

can_view = require_permission(PermissionCode.POSITION_VIEW)
can_manage = require_permission(PermissionCode.BANKS_MANAGE)


@router.get("", response_model=list[AccountOut])
def list_accounts(
    # Obligatoire : une réponse ne mélange jamais les comptes de deux sociétés
    company_id: int = Query(description="Société dont on veut les comptes"),
    bank_id: int | None = None,
    devise: str | None = Query(default=None, pattern=r"^[A-Za-z]{3}$"),
    actif: bool | None = None,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_view),
) -> list[AccountOut]:
    accounts = account_service.list_accounts(
        db,
        company_id=company_id,
        bank_id=bank_id,
        devise=devise.upper() if devise else None,
        actif=actif,
    )
    return [AccountOut.from_model(account) for account in accounts]


@router.get("/{account_id}", response_model=AccountOut)
def get_account(
    account_id: int, db: Session = Depends(get_db), _user: CurrentUser = Depends(can_view)
) -> AccountOut:
    return AccountOut.from_model(account_service.get_account(db, account_id))


@router.post("", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
def create_account(
    body: AccountCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_manage),
) -> AccountOut:
    account = account_service.create_account(
        db,
        **body.model_dump(),
        acteur_id=user.id,
        ip=client_ip(request),
    )
    return AccountOut.from_model(account)


@router.put("/{account_id}", response_model=AccountOut)
def update_account(
    account_id: int,
    body: AccountUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_manage),
) -> AccountOut:
    account = account_service.update_account(
        db,
        account_id,
        **body.model_dump(),
        acteur_id=user.id,
        ip=client_ip(request),
    )
    return AccountOut.from_model(account)


@router.patch("/{account_id}/status", response_model=AccountOut)
def set_account_status(
    account_id: int,
    body: AccountStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_manage),
) -> AccountOut:
    account = account_service.set_account_status(
        db, account_id, actif=body.actif, acteur_id=user.id, ip=client_ip(request)
    )
    return AccountOut.from_model(account)
