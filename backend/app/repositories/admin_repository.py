"""Lectures et écritures de l'administration (P16.1) : utilisateurs, rôles, permissions."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Permission, Role, User, UserRole

ROLE_ADMIN = "ADMIN"


def list_users(db: Session) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .options(selectinload(User.roles), selectinload(User.permissions_perso))
            .order_by(func.lower(User.nom))
        )
    )


def get_user(db: Session, user_id: int) -> User | None:
    return db.scalar(select(User).options(selectinload(User.roles)).where(User.id == user_id))


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def list_roles(db: Session) -> list[Role]:
    """Rôles système d'abord, puis les rôles personnalisés, dans l'ordre de création."""
    return list(
        db.scalars(
            select(Role)
            .options(selectinload(Role.permissions), selectinload(Role.users))
            .order_by(Role.systeme.desc(), Role.id)
        )
    )


def get_role(db: Session, role_id: int, *, lock: bool = False) -> Role | None:
    query = (
        select(Role)
        .options(selectinload(Role.permissions), selectinload(Role.users))
        .where(Role.id == role_id)
    )
    if lock:
        query = query.with_for_update()
    return db.scalar(query)


def get_role_by_code(db: Session, code: str) -> Role | None:
    return db.scalar(select(Role).where(Role.code == code))


def get_role_by_nom(db: Session, nom: str) -> Role | None:
    return db.scalar(select(Role).where(func.lower(Role.nom) == nom.lower()))


def get_roles(db: Session, role_ids: list[int]) -> list[Role]:
    return list(db.scalars(select(Role).where(Role.id.in_(role_ids))))


def list_permissions(db: Session) -> list[Permission]:
    return list(db.scalars(select(Permission).order_by(Permission.code)))


def get_permissions_by_codes(db: Session, codes: list[str]) -> list[Permission]:
    return list(db.scalars(select(Permission).where(Permission.code.in_(codes))))


def lock_admin_role(db: Session) -> None:
    """Verrou de la règle « au moins un administrateur actif » : deux changements simultanés ne
    peuvent pas retirer chacun l'avant-dernier administrateur."""
    db.execute(select(Role.id).where(Role.code == ROLE_ADMIN).with_for_update())


def count_active_admins(db: Session) -> int:
    return (
        db.scalar(
            select(func.count(func.distinct(User.id)))
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(Role.code == ROLE_ADMIN, User.actif.is_(True))
        )
        or 0
    )


def add(db: Session, obj):
    db.add(obj)
    db.flush()
    return obj


def delete(db: Session, obj) -> None:
    db.delete(obj)
    db.flush()
