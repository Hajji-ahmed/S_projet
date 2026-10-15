"""Dashboard (P15, 14/10/2026) : la vue d'ensemble d'une société sur une période."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.db import get_db
from app.core.permissions import PermissionCode
from app.schemas.dashboard import AlerteOut, AlertesOut, DashboardOut
from app.services import dashboard_service
from app.services.auth_service import CurrentUser

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

can_view = require_permission(PermissionCode.DASHBOARD_VIEW)


@router.get("", response_model=DashboardOut)
def lire(
    company_id: Annotated[int, Query(description="Société affichée")],
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_view),
) -> DashboardOut:
    """KPI, évolution des soldes, frais, comptes, dernières opérations et alertes de la période
    (par défaut, le mois en cours)."""
    return DashboardOut.of(
        dashboard_service.dashboard(db, company_id, date_from=date_from, date_to=date_to)
    )


@router.get("/alertes", response_model=AlertesOut)
def lire_alertes(
    company_id: Annotated[int, Query(description="Société affichée")],
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_view),
) -> AlertesOut:
    """Alertes du mois en cours : la cloche de l'en-tête."""
    vue = dashboard_service.dashboard(db, company_id)
    return AlertesOut(alertes=[AlerteOut.of(alerte) for alerte in vue.alertes])
