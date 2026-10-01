from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_user
from app.core.config import get_settings
from app.core.db import get_db
from app.schemas.auth import CurrentUserOut, LoginRequest, TokenResponse
from app.services import auth_service
from app.services.auth_service import AuthenticationError, AuthResult, CurrentUser

# Cookie de session : invisible du JavaScript (HttpOnly), envoyé seulement aux routes /api/auth
SESSION_COOKIE = "simtis_session"
SESSION_COOKIE_PATH = "/api/auth"

# Routes publiques : connexion, rafraîchissement et déconnexion se font sans jeton d'accès
public_router = APIRouter(prefix="/auth", tags=["auth"])
# Routes qui exigent un utilisateur connecté
protected_router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(result: AuthResult) -> TokenResponse:
    return TokenResponse(
        access_token=result.access_token,
        expires_in=result.expires_in,
        user=CurrentUserOut.from_user(result.user),
    )


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_hours * 3600,
        path=SESSION_COOKIE_PATH,
        httponly=True,
        secure=settings.is_production,
        samesite="strict",
    )


def _clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        SESSION_COOKIE,
        path=SESSION_COOKIE_PATH,
        httponly=True,
        secure=settings.is_production,
        samesite="strict",
    )


@public_router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)
) -> TokenResponse:
    try:
        result = auth_service.login(
            db,
            body.email,
            body.password,
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except AuthenticationError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error
    _set_session_cookie(response, result.session_token)
    return _token_response(result)


@public_router.post("/refresh", response_model=TokenResponse)
def refresh(
    response: Response,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> TokenResponse:
    try:
        result = auth_service.refresh(db, session_token)
    except AuthenticationError as error:
        # Le cookie n'est plus valable : on le retire pour ne plus le renvoyer à chaque requête.
        # Les en-têtes d'une HTTPException remplacent ceux de `response` : la suppression est copiée.
        _clear_session_cookie(response)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
            headers={"set-cookie": response.headers["set-cookie"]},
        ) from error
    return _token_response(result)


@public_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> None:
    auth_service.logout(db, session_token, ip=client_ip(request))
    _clear_session_cookie(response)


@protected_router.get("/me", response_model=CurrentUserOut)
def me(user: CurrentUser = Depends(get_current_user)) -> CurrentUserOut:
    return CurrentUserOut.from_user(user)
