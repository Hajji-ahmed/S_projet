"""Administration (P16.1) : utilisateurs (`admin.users`), rôles et permissions (`admin.roles`)."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import client_ip, require_any_permission, require_permission
from app.core.db import get_db
from app.core.permissions import PermissionCode
from app.schemas.admin import (
    PasswordOut,
    PermissionOut,
    PermissionPersonneOut,
    PermissionsPersonneIn,
    RoleIn,
    RoleOut,
    UserIn,
    UserOut,
    UserStatusIn,
)
from app.services import admin_service
from app.services.auth_service import CurrentUser

router = APIRouter(prefix="/admin", tags=["administration"])

can_users = require_permission(PermissionCode.ADMIN_USERS)
can_roles = require_permission(PermissionCode.ADMIN_ROLES)
# Le formulaire d'un utilisateur liste les rôles ; la matrice les modifie
can_read_roles = require_any_permission(PermissionCode.ADMIN_USERS, PermissionCode.ADMIN_ROLES)


def _out(user) -> UserOut:
    return UserOut.of(user, now=datetime.now(UTC))


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _user: CurrentUser = Depends(can_users)):
    return [_out(user) for user in admin_service.list_users(db)]


@router.post("/users", response_model=PasswordOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_users),
) -> PasswordOut:
    """Crée le compte avec un mot de passe provisoire, renvoyé une seule fois."""
    result = admin_service.create_user(
        db,
        nom=body.nom,
        email=body.email,
        role_ids=body.role_ids,
        acteur_id=user.id,
        ip=client_ip(request),
    )
    return PasswordOut(user=_out(result.user), mot_de_passe=result.mot_de_passe)


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_users),
) -> UserOut:
    return _out(
        admin_service.update_user(
            db,
            user_id,
            nom=body.nom,
            email=body.email,
            role_ids=body.role_ids,
            acteur_id=user.id,
            ip=client_ip(request),
        )
    )


@router.get("/users/{user_id}/permissions", response_model=list[PermissionPersonneOut])
def user_permissions(
    user_id: int,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_users),
) -> list[PermissionPersonneOut]:
    """Permissions de la personne : origine (rôles, ajout, retrait) et état final (23/10/2026)."""
    return [PermissionPersonneOut.of(item) for item in admin_service.user_permissions(db, user_id)]


@router.put("/users/{user_id}/permissions", response_model=list[PermissionPersonneOut])
def set_user_permissions(
    user_id: int,
    body: PermissionsPersonneIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_users),
) -> list[PermissionPersonneOut]:
    """Remplace les ajouts et retraits de permissions de la personne, tout ou rien."""
    items = admin_service.set_user_permissions(
        db,
        user_id,
        ajouts=body.ajouts,
        retraits=body.retraits,
        acteur_id=user.id,
        ip=client_ip(request),
    )
    return [PermissionPersonneOut.of(item) for item in items]


@router.patch("/users/{user_id}/status", response_model=UserOut)
def set_status(
    user_id: int,
    body: UserStatusIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_users),
) -> UserOut:
    return _out(
        admin_service.set_active(
            db, user_id, actif=body.actif, acteur_id=user.id, ip=client_ip(request)
        )
    )


@router.post("/users/{user_id}/password", response_model=PasswordOut)
def reset_password(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_users),
) -> PasswordOut:
    result = admin_service.reset_password(db, user_id, acteur_id=user.id, ip=client_ip(request))
    return PasswordOut(user=_out(result.user), mot_de_passe=result.mot_de_passe)


@router.get("/roles", response_model=list[RoleOut])
def list_roles(db: Session = Depends(get_db), _user: CurrentUser = Depends(can_read_roles)):
    return [RoleOut.of(role) for role in admin_service.list_roles(db)]


@router.get("/permissions", response_model=list[PermissionOut])
def list_permissions(db: Session = Depends(get_db), _user: CurrentUser = Depends(can_roles)):
    return [PermissionOut.of(info) for info in admin_service.list_permissions(db)]


@router.post("/roles", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
def create_role(
    body: RoleIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_roles),
) -> RoleOut:
    return RoleOut.of(
        admin_service.create_role(
            db,
            nom=body.nom,
            description=body.description,
            permission_codes=body.permissions,
            acteur_id=user.id,
            ip=client_ip(request),
        )
    )


@router.put("/roles/{role_id}", response_model=RoleOut)
def update_role(
    role_id: int,
    body: RoleIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_roles),
) -> RoleOut:
    return RoleOut.of(
        admin_service.update_role(
            db,
            role_id,
            nom=body.nom,
            description=body.description,
            permission_codes=body.permissions,
            acteur_id=user.id,
            ip=client_ip(request),
        )
    )


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(
    role_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_roles),
) -> Response:
    admin_service.delete_role(db, role_id, acteur_id=user.id, ip=client_ip(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
