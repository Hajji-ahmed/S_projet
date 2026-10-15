"""Rapports Excel (P16.4) : position du jour (`position.view`), état de rapprochement
(`reconciliation.view`)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import client_ip, require_permission
from app.core.db import get_db
from app.core.permissions import PermissionCode
from app.services import rapports_service
from app.services.auth_service import CurrentUser

router = APIRouter(prefix="/rapports", tags=["rapports"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _fichier(nom: str, contenu: bytes) -> Response:
    return Response(
        content=contenu,
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{nom}"'},
    )


@router.get("/position", response_class=Response, responses={200: {"content": {XLSX: {}}}})
def position_du_jour(
    request: Request,
    company_id: Annotated[int, Query(description="Société")],
    jour: Annotated[date | None, Query(alias="date")] = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission(PermissionCode.POSITION_VIEW)),
) -> Response:
    """Tableau Banques à la date (aujourd'hui par défaut), dans sa structure imposée."""
    return _fichier(
        *rapports_service.position_du_jour(
            db, company_id, jour, acteur_id=user.id, ip=client_ip(request)
        )
    )


@router.get("/rapprochement", response_class=Response, responses={200: {"content": {XLSX: {}}}})
def etat_rapprochement(
    request: Request,
    company_id: Annotated[int, Query(description="Société")],
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission(PermissionCode.RECONCILIATION_VIEW)),
) -> Response:
    """Synthèse par compte (par statut) et opérations restant à rapprocher sur la période."""
    return _fichier(
        *rapports_service.etat_rapprochement(
            db, company_id, date_from, date_to, acteur_id=user.id, ip=client_ip(request)
        )
    )
