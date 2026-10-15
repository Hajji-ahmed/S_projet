"""Administration (P16.1) : utilisateurs, rôles, permissions."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import Role, User
from app.services.admin_service import PermissionInfo


class RoleRef(BaseModel):
    id: int
    code: str
    nom: str


class UserOut(BaseModel):
    id: int
    nom: str
    email: str
    actif: bool
    roles: list[RoleRef]
    dernier_login: datetime | None
    verrouille: bool
    created_at: datetime

    @classmethod
    def of(cls, user: User, *, now: datetime) -> "UserOut":
        return cls(
            id=user.id,
            nom=user.nom,
            email=user.email,
            actif=user.actif,
            roles=[
                RoleRef(id=role.id, code=role.code, nom=role.nom)
                for role in sorted(user.roles, key=lambda r: r.nom)
            ],
            dernier_login=user.dernier_login,
            verrouille=user.verrouille_jusqu_a is not None and user.verrouille_jusqu_a > now,
            created_at=user.created_at,
        )


class UserIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nom: str = Field(max_length=120)
    email: str = Field(max_length=255)
    role_ids: list[int]


class UserStatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actif: bool


class PasswordOut(BaseModel):
    """Mot de passe provisoire : à transmettre à l'utilisateur, il n'est plus jamais affiché."""

    user: UserOut
    mot_de_passe: str


class RoleOut(BaseModel):
    id: int
    code: str
    nom: str
    description: str | None
    systeme: bool
    permissions: list[str]
    nb_utilisateurs: int

    @classmethod
    def of(cls, role: Role) -> "RoleOut":
        return cls(
            id=role.id,
            code=role.code,
            nom=role.nom,
            description=role.description,
            systeme=role.systeme,
            permissions=sorted(permission.code for permission in role.permissions),
            nb_utilisateurs=len(role.users),
        )


class RoleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nom: str = Field(max_length=80)
    description: str | None = Field(default=None, max_length=500)
    permissions: list[str]


class PermissionOut(BaseModel):
    code: str
    description: str
    module: str

    @classmethod
    def of(cls, info: PermissionInfo) -> "PermissionOut":
        return cls(code=info.code, description=info.description, module=info.module)
