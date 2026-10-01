from typing import Literal

from pydantic import BaseModel, Field

from app.services.auth_service import CurrentUser


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=256)


class CurrentUserOut(BaseModel):
    id: int
    nom: str
    email: str
    roles: list[str]
    permissions: list[str]

    @classmethod
    def from_user(cls, user: CurrentUser) -> "CurrentUserOut":
        return cls(
            id=user.id,
            nom=user.nom,
            email=user.email,
            roles=list(user.roles),
            permissions=sorted(user.permissions),
        )


class TokenResponse(BaseModel):
    """Jeton d'accès (à garder en mémoire côté navigateur) et utilisateur connecté."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Durée de validité du jeton d'accès, en secondes")
    user: CurrentUserOut
