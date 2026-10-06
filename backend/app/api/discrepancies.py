"""Écarts (P12) : suivi des anomalies du rapprochement, jusqu'à leur clôture commentée."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import client_ip, require_permission
from app.core.db import get_db
from app.core.permissions import PermissionCode
from app.schemas.discrepancy import (
    ClotureIn,
    EcartDetailOut,
    EcartIn,
    EcartsPageOut,
    EcartUpdateIn,
    GenerationIn,
    GenerationOut,
    ResponsableOut,
    StatutEcart,
    TypeEcart,
)
from app.services import discrepancy_service
from app.services.auth_service import CurrentUser

router = APIRouter(prefix="/discrepancies", tags=["discrepancies"])

can_view = require_permission(PermissionCode.RECONCILIATION_VIEW)
can_manage = require_permission(PermissionCode.DISCREPANCIES_MANAGE)


def _detail(db: Session, discrepancy_id: int) -> EcartDetailOut:
    return EcartDetailOut.from_detail(discrepancy_service.get_detail(db, discrepancy_id))


@router.get("", response_model=EcartsPageOut)
def list_discrepancies(
    company_id: Annotated[int, Query(description="Société dont on veut les écarts")],
    statut: StatutEcart | None = None,
    type: TypeEcart | None = None,
    responsable_id: int | None = None,
    bank_account_id: int | None = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    q: Annotated[str | None, Query(max_length=100, description="Libellé, pièce, tiers")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_view),
) -> EcartsPageOut:
    """Écarts de la société, des plus récents aux plus anciens, 50 par page."""
    result = discrepancy_service.list_discrepancies(
        db,
        company_id,
        statut=statut,
        type_ecart=type,
        responsable_id=responsable_id,
        bank_account_id=bank_account_id,
        date_from=date_from,
        date_to=date_to,
        q=q,
        page=page,
    )
    return EcartsPageOut.from_page(result)


@router.get("/responsables", response_model=list[ResponsableOut])
def list_responsables(
    company_id: Annotated[int, Query(description="Société des écarts")],
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_view),
) -> list[ResponsableOut]:
    """Utilisateurs actifs à qui un écart peut être confié."""
    return [ResponsableOut.of(user) for user in discrepancy_service.responsables(db, company_id)]


@router.get("/{discrepancy_id}", response_model=EcartDetailOut)
def get_discrepancy(
    discrepancy_id: int, db: Session = Depends(get_db), _user: CurrentUser = Depends(can_view)
) -> EcartDetailOut:
    """Un écart, ses lignes et son historique complet."""
    return _detail(db, discrepancy_id)


@router.post("", response_model=EcartDetailOut, status_code=201)
def create_discrepancy(
    body: EcartIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_manage),
) -> EcartDetailOut:
    """Signale un écart sur une opération et / ou une écriture."""
    ecart = discrepancy_service.create(
        db,
        type_ecart=body.type,
        transaction_id=body.transaction_id,
        entry_id=body.ecriture_id,
        commentaire=body.commentaire,
        responsable_id=body.responsable_id,
        acteur_id=user.id,
        ip=client_ip(request),
    )
    return _detail(db, ecart.id)


@router.post("/generate", response_model=GenerationOut)
def generate_discrepancies(
    body: GenerationIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_manage),
) -> GenerationOut:
    """Crée les écarts de la période : doublons potentiels, lignes restées sans pendant."""
    result = discrepancy_service.generate(
        db,
        company_id=body.company_id,
        bank_account_id=body.bank_account_id,
        date_from=body.du,
        date_to=body.au,
        acteur_id=user.id,
        ip=client_ip(request),
    )
    return GenerationOut.from_result(result)


@router.patch("/{discrepancy_id}", response_model=EcartDetailOut)
def update_discrepancy(
    discrepancy_id: int,
    body: EcartUpdateIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_manage),
) -> EcartDetailOut:
    """Fait avancer l'écart (En cours, Traité), change son responsable ou son commentaire."""
    changes = {name: getattr(body, name) for name in body.model_fields_set}
    discrepancy_service.update(
        db, discrepancy_id, **changes, acteur_id=user.id, ip=client_ip(request)
    )
    return _detail(db, discrepancy_id)


@router.post("/{discrepancy_id}/close", response_model=EcartDetailOut)
def close_discrepancy(
    discrepancy_id: int,
    body: ClotureIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_manage),
) -> EcartDetailOut:
    """Clôture l'écart (commentaire obligatoire) ; ses lignes redeviennent « Non rapprochée »."""
    discrepancy_service.close(
        db,
        discrepancy_id,
        commentaire=body.commentaire,
        acteur_id=user.id,
        ip=client_ip(request),
    )
    return _detail(db, discrepancy_id)
