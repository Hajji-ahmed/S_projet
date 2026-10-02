from datetime import date

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import client_ip, require_permission
from app.core.db import get_db
from app.core.permissions import PermissionCode
from app.models import BankAccount
from app.schemas.account import AccountCreate, AccountOut, AccountStatusUpdate, AccountUpdate
from app.schemas.balance import BalanceIn, BalanceOut
from app.services import account_service, balance_service
from app.services.auth_service import CurrentUser

router = APIRouter(prefix="/accounts", tags=["accounts"])

can_view = require_permission(PermissionCode.POSITION_VIEW)
can_manage = require_permission(PermissionCode.BANKS_MANAGE)


def _out(db: Session, account: BankAccount) -> AccountOut:
    """Compte avec ses chiffres à aujourd'hui."""
    figures = balance_service.figures_for_accounts(db, [account])
    return AccountOut.from_model(account, figures[account.id])


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
    figures = balance_service.figures_for_accounts(db, accounts)
    return [AccountOut.from_model(account, figures[account.id]) for account in accounts]


@router.get("/{account_id}", response_model=AccountOut)
def get_account(
    account_id: int, db: Session = Depends(get_db), _user: CurrentUser = Depends(can_view)
) -> AccountOut:
    account = account_service.get_account(db, account_id)
    return _out(db, account)


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
    return _out(db, account)


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
    return _out(db, account)


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
    return _out(db, account)


@router.get("/{account_id}/balances", response_model=list[BalanceOut])
def list_balances(
    account_id: int,
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_view),
) -> list[BalanceOut]:
    """Historique des soldes, du plus récent au plus ancien (30 derniers jours par défaut)."""
    rows = balance_service.list_balances(db, account_id, date_from, date_to)
    return [BalanceOut.from_row(balance, saisi_par) for balance, saisi_par in rows]


@router.put("/{account_id}/balances/{jour}", response_model=BalanceOut)
def save_balance(
    account_id: int,
    jour: date,
    body: BalanceIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_manage),
) -> BalanceOut:
    """Saisit, ou corrige, le solde et le crédit utilisé d'un compte pour une date."""
    balance = balance_service.save_balance(
        db,
        account_id,
        jour,
        solde=body.solde,
        credit_utilise=body.credit_utilise,
        commentaire=body.commentaire,
        acteur_id=user.id,
        ip=client_ip(request),
    )
    return BalanceOut.from_row(balance, user.nom)
