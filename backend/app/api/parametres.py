"""Paramètres (P16.3) : grille de rapprochement et modèles de mapping, `admin.settings`."""

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import client_ip, require_permission
from app.core.db import get_db
from app.core.permissions import PermissionCode
from app.schemas.parametres import GrilleIn, MappingOut, RegleOut
from app.services import parametres_service
from app.services.auth_service import CurrentUser
from app.services.parametres_service import Changement

router = APIRouter(prefix="/parametres", tags=["paramètres"])

can_manage = require_permission(PermissionCode.ADMIN_SETTINGS)


@router.get("/rapprochement", response_model=list[RegleOut])
def lire_grille(db: Session = Depends(get_db), _user: CurrentUser = Depends(can_manage)):
    return [RegleOut.of(rule) for rule in parametres_service.grille(db)]


@router.put("/rapprochement", response_model=list[RegleOut])
def modifier_grille(
    body: GrilleIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_manage),
):
    """Tout ou rien ; vaut pour le prochain lancement du moteur."""
    rules = parametres_service.modifier_grille(
        db,
        [Changement(r.code, r.poids, r.tolerance, r.actif) for r in body.regles],
        acteur_id=user.id,
        ip=client_ip(request),
    )
    return [RegleOut.of(rule) for rule in rules]


@router.get("/mappings", response_model=list[MappingOut])
def lire_mappings(db: Session = Depends(get_db), _user: CurrentUser = Depends(can_manage)):
    return [MappingOut.of(mapping) for mapping in parametres_service.mappings(db)]


@router.delete("/mappings/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
def supprimer_mapping(
    mapping_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_manage),
) -> Response:
    parametres_service.supprimer_mapping(db, mapping_id, acteur_id=user.id, ip=client_ip(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
