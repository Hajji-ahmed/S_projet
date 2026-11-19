"""Dépendances communes des endpoints : utilisateur connecté (401) et permissions (403)."""

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.permissions import PermissionCode
from app.core.security import InvalidTokenError, decode_access_token
from app.services import acces_societe_service, auth_service
from app.services.auth_service import CurrentUser

_bearer = HTTPBearer(auto_error=False)

NOT_AUTHENTICATED = "Authentification requise."


def _unauthorized(detail: str = NOT_AUTHENTICATED) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> CurrentUser:
    """Utilisateur du jeton d'accès. 401 si le jeton manque, est invalide, ou si la session est fermée."""
    if credentials is None:
        raise _unauthorized()
    try:
        claims = decode_access_token(credentials.credentials)
    except InvalidTokenError as error:
        raise _unauthorized() from error

    user = auth_service.load_current_user(db, claims.user_id, claims.session_id)
    if user is None:
        raise _unauthorized(auth_service.SESSION_EXPIRED_MESSAGE)
    return user


def verifier_societe(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Dépendance de `protected_router` (19/11/2026) : refuse (403) toute route dont un paramètre
    de chemin ou de requête (company_id, account_id, transaction_id...) appartient à une société que
    la personne n'a pas le droit de voir. Les corps JSON et formulaires sont vérifiés par la route."""
    parametres: dict[str, list[str]] = {
        nom: [str(valeur)] for nom, valeur in request.path_params.items()
    }
    for nom in request.query_params:
        parametres.setdefault(nom, []).extend(request.query_params.getlist(nom))
    acces_societe_service.verifier_parametres(db, user, parametres)


def require_permission(code: PermissionCode) -> Callable[..., CurrentUser]:
    """Dépendance qui exige une permission : `user = Depends(require_permission(PermissionCode.X))`."""

    def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not user.has_permission(code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission requise : {code.value}.",
            )
        return user

    return dependency


def require_any_permission(*codes: PermissionCode) -> Callable[..., CurrentUser]:
    """Dépendance qui exige AU MOINS UNE des permissions (lecture partagée entre deux métiers)."""

    def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not any(user.has_permission(code) for code in codes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission requise : " + " ou ".join(code.value for code in codes) + ".",
            )
        return user

    return dependency


def client_ip(request: Request) -> str | None:
    """Adresse IP du client. En production (derrière Caddy), uvicorn --proxy-headers la lit dans
    l'en-tête X-Forwarded-For du proxy (Dockerfile.prod)."""
    return request.client.host if request.client else None
