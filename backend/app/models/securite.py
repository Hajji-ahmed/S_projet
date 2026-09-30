"""Utilisateurs, rôles, permissions (RBAC dynamique) et journal d'audit."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("email = lower(email)", name="email_minuscules"),)

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    nom: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    mot_de_passe_hash: Mapped[str] = mapped_column(String(255))
    actif: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    dernier_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    roles: Mapped[list["Role"]] = relationship(secondary="user_roles", back_populates="users")


class Role(TimestampMixin, Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    nom: Mapped[str] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)
    # Les rôles « système » (Administrateur...) ne peuvent pas être supprimés depuis l'interface
    systeme: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    users: Mapped[list[User]] = relationship(secondary="user_roles", back_populates="roles")
    permissions: Mapped[list["Permission"]] = relationship(
        secondary="role_permissions", back_populates="roles"
    )


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    code: Mapped[str] = mapped_column(String(60), unique=True)
    description: Mapped[str | None] = mapped_column(Text)

    roles: Mapped[list[Role]] = relationship(
        secondary="role_permissions", back_populates="permissions"
    )


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )


class AuditLog(Base):
    """Journal des actions sensibles. Ajout seul : un trigger PostgreSQL refuse UPDATE et DELETE."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_entite", "entite", "entite_id"),
        Index("ix_audit_logs_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    # Pas de clé étrangère : le journal doit survivre à la suppression d'un utilisateur
    user_id: Mapped[int | None] = mapped_column(index=True)
    action: Mapped[str] = mapped_column(String(60))
    entite: Mapped[str] = mapped_column(String(60))
    entite_id: Mapped[str | None] = mapped_column(String(60))
    ancienne_valeur: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    nouvelle_valeur: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
