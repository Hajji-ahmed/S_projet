"""Historique (P16.2) : lecture du journal d'audit, permission `audit.view`."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.db import get_db
from app.core.permissions import PermissionCode
from app.schemas.historique import DetailOut, FiltresOut, PageOut
from app.services import historique_service
from app.services.auth_service import CurrentUser

router = APIRouter(prefix="/audit", tags=["historique"])

can_view = require_permission(PermissionCode.AUDIT_VIEW)


@router.get("", response_model=PageOut)
def lire(
    page: Annotated[int, Query(ge=1)] = 1,
    user_id: int | None = None,
    action: str | None = None,
    entite: str | None = None,
    entite_id: str | None = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_view),
) -> PageOut:
    """Du plus récent au plus ancien, 50 par page ; dates en jours du Maroc."""
    return PageOut.of(
        historique_service.journal(
            db,
            page=page,
            user_id=user_id,
            action=action,
            entite=entite,
            entite_id=entite_id,
            date_from=date_from,
            date_to=date_to,
        )
    )


@router.get("/filtres", response_model=FiltresOut)
def lire_filtres(
    db: Session = Depends(get_db), _user: CurrentUser = Depends(can_view)
) -> FiltresOut:
    return FiltresOut.of(historique_service.filtres(db))


@router.get("/{audit_id}", response_model=DetailOut)
def lire_detail(
    audit_id: int, db: Session = Depends(get_db), _user: CurrentUser = Depends(can_view)
) -> DetailOut:
    return DetailOut.of(historique_service.detail(db, audit_id))
