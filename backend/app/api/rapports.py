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
PDF = "application/pdf"


def _fichier(nom: str, contenu: bytes, media_type: str = XLSX) -> Response:
    return Response(
        content=contenu,
        media_type=media_type,
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


@router.get("/position/pdf", response_class=Response, responses={200: {"content": {PDF: {}}}})
def position_pdf(
    request: Request,
    company_id: Annotated[int, Query(description="Société")],
    jour: Annotated[date | None, Query(alias="date")] = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission(PermissionCode.POSITION_VIEW)),
) -> Response:
    """Même tableau Banques en PDF A4 paysage (27/10/2026)."""
    nom, contenu = rapports_service.position_pdf(
        db, company_id, jour, acteur_id=user.id, ip=client_ip(request)
    )
    return _fichier(nom, contenu, PDF)


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


@router.get("/non-rapproches", response_class=Response, responses={200: {"content": {XLSX: {}}}})
def non_rapproches(
    request: Request,
    company_id: Annotated[int, Query(description="Société")],
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    bank_id: Annotated[int | None, Query(description="Banque (toutes sans valeur)")] = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission(PermissionCode.RECONCILIATION_VIEW)),
) -> Response:
    """Opérations et écritures non rapprochées de la période, côte à côte par compte (30/10/2026)."""
    return _fichier(
        *rapports_service.non_rapproches(
            db, company_id, date_from, date_to, bank_id, acteur_id=user.id, ip=client_ip(request)
        )
    )
