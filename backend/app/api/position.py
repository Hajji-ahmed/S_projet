from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import client_ip, require_permission
from app.core.db import get_db
from app.core.permissions import PermissionCode
from app.schemas.position import BanquesTableOut, DevisesSoldesOut
from app.schemas.saisie import DevisesIn, DevisesOut, PrevisionsIn, PrevisionsOut
from app.services import position_banques_service, position_service, saisie_service
from app.services.auth_service import CurrentUser

router = APIRouter(prefix="/position", tags=["position"])

can_view = require_permission(PermissionCode.POSITION_VIEW)
can_enter_devises = require_permission(PermissionCode.BANKS_MANAGE)
can_enter_previsions = require_permission(PermissionCode.FORECASTS_MANAGE)

# Une grille appartient à UNE société et à UNE date
CompanyId = Annotated[int, Query(description="Société de la grille")]
Jour = Annotated[date, Query(alias="date", description="Date de la grille (AAAA-MM-JJ)")]
JourOuAujourdhui = Annotated[
    date | None, Query(alias="date", description="Date de la grille, aujourd'hui par défaut")
]


@router.get("/banques", response_model=BanquesTableOut)
def get_banques(
    company_id: CompanyId,
    jour: JourOuAujourdhui = None,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_view),
) -> BanquesTableOut:
    """Tableau Banques calculé à partir des soldes du jour, jusqu'à la date (jamais après aujourd'hui)."""
    table = position_banques_service.banques_table(db, company_id, jour)
    return BanquesTableOut.from_table(company_id, table)


@router.get("/devises/soldes", response_model=DevisesSoldesOut)
def get_devises_soldes(
    company_id: CompanyId,
    jour: JourOuAujourdhui = None,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_view),
) -> DevisesSoldesOut:
    """Lignes EUR et USD du tableau Devises : soldes des comptes en devise, sans conversion."""
    table = position_banques_service.devises_table(db, company_id, jour)
    return DevisesSoldesOut.from_table(company_id, table)


@router.get("/devises", response_model=DevisesOut)
def get_devises(
    company_id: CompanyId,
    jour: JourOuAujourdhui = None,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_view),
) -> DevisesOut:
    jour = jour or position_service.business_today()
    rows = saisie_service.list_devises(db, company_id, jour)
    return DevisesOut.from_rows(company_id, jour, rows)


@router.put("/devises", response_model=DevisesOut)
def save_devises(
    company_id: CompanyId,
    jour: Jour,
    body: DevisesIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_enter_devises),
) -> DevisesOut:
    """Enregistre la grille Devises de la date. Une cellule absente ou `null` est vidée."""
    rows = saisie_service.save_devises(
        db, company_id, jour, body.cells(), acteur_id=user.id, ip=client_ip(request)
    )
    return DevisesOut.from_rows(company_id, jour, rows)


@router.get("/previsions", response_model=PrevisionsOut)
def get_previsions(
    company_id: CompanyId,
    jour: JourOuAujourdhui = None,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_view),
) -> PrevisionsOut:
    jour = jour or position_service.business_today()
    rows, days = saisie_service.list_previsions(db, company_id, jour)
    return PrevisionsOut.from_rows(company_id, jour, rows, days)


@router.put("/previsions", response_model=PrevisionsOut)
def save_previsions(
    company_id: CompanyId,
    jour: Jour,
    body: PrevisionsIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_enter_previsions),
) -> PrevisionsOut:
    """Enregistre la grille Prévisions de la date. Une cellule absente ou `null` est vidée."""
    rows, days = saisie_service.save_previsions(
        db,
        company_id,
        jour,
        body.cells(),
        body.jour_values(),
        acteur_id=user.id,
        ip=client_ip(request),
    )
    return PrevisionsOut.from_rows(company_id, jour, rows, days)
