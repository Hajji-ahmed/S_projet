from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Permission, Role, RolePermission, User, UserRole, UserSession


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def get_user(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def get_role_names(db: Session, user_id: int) -> list[str]:
    query = (
        select(Role.nom)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
        .order_by(Role.nom)
    )
    return list(db.scalars(query))


def get_permission_codes(db: Session, user_id: int) -> set[str]:
    """Permissions effectives : l'union des permissions de tous les rôles de l'utilisateur."""
    query = (
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id)
        .distinct()
    )
    return set(db.scalars(query))


def get_roles_by_codes(db: Session, codes: list[str]) -> list[Role]:
    return list(db.scalars(select(Role).where(Role.code.in_(codes))))


def add_user(db: Session, user: User) -> User:
    db.add(user)
    db.flush()
    return user


def add_session(db: Session, session: UserSession) -> UserSession:
    db.add(session)
    db.flush()
    return session


def get_session_by_hash(db: Session, token_hash: str) -> UserSession | None:
    return db.scalar(select(UserSession).where(UserSession.token_hash == token_hash))


def get_active_session_user(
    db: Session, user_id: int, session_id: int, now: datetime
) -> User | None:
    """L'utilisateur, seulement s'il est actif et si cette session lui appartient et reste valide."""
    query = (
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(
            User.id == user_id,
            User.actif.is_(True),
            UserSession.id == session_id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )
    )
    return db.scalar(query)


def revoke_user_sessions(db: Session, user_id: int, now: datetime) -> int:
    """Révoque toutes les sessions encore ouvertes d'un utilisateur. Retourne leur nombre."""
    result = db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    return result.rowcount
