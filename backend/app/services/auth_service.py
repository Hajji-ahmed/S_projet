"""Authentification : connexion, verrouillage, sessions, comptes.

Chaque fonction publique valide sa transaction (`commit`) : un échec de connexion doit être compté et
tracé même si la requête se termine par une erreur 401.
"""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core import security
from app.core.config import get_settings
from app.models import User, UserSession
from app.repositories import auth_repository
from app.services import audit_service

# Message unique pour tout refus de connexion : il ne révèle jamais si l'email existe
LOGIN_FAILED_MESSAGE = "Email ou mot de passe incorrect."
SESSION_EXPIRED_MESSAGE = "Session expirée. Veuillez vous reconnecter."


class AuthenticationError(Exception):
    """Refus d'authentification. Le message est destiné à l'utilisateur."""


class AccountError(Exception):
    """Erreur de gestion de compte (email déjà utilisé, rôle inconnu, mot de passe trop court...)."""


@dataclass(frozen=True)
class CurrentUser:
    id: int
    session_id: int
    nom: str
    email: str
    roles: tuple[str, ...]
    permissions: frozenset[str]

    def has_permission(self, code: str) -> bool:
        return code in self.permissions


@dataclass(frozen=True)
class AuthResult:
    access_token: str
    expires_in: int
    user: CurrentUser


@dataclass(frozen=True)
class LoginResult(AuthResult):
    session_token: str
    session_expires_at: datetime


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(UTC)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _current_user(db: Session, user: User, session_id: int) -> CurrentUser:
    return CurrentUser(
        id=user.id,
        session_id=session_id,
        nom=user.nom,
        email=user.email,
        roles=tuple(auth_repository.get_role_names(db, user.id)),
        permissions=frozenset(auth_repository.get_permission_codes(db, user.id)),
    )


def _auth_result(db: Session, user: User, session_id: int, now: datetime) -> AuthResult:
    settings = get_settings()
    return AuthResult(
        access_token=security.create_access_token(user.id, session_id, now=now),
        expires_in=settings.access_token_minutes * 60,
        user=_current_user(db, user, session_id),
    )


def _refuse_login(
    db: Session,
    *,
    email: str,
    motif: str,
    user: User | None = None,
    ip: str | None = None,
) -> AuthenticationError:
    audit_service.log(
        db,
        user_id=user.id if user else None,
        action="echec_connexion",
        entite="user",
        entite_id=user.id if user else None,
        apres={"email": email, "motif": motif},
        ip=ip,
    )
    db.commit()
    return AuthenticationError(LOGIN_FAILED_MESSAGE)


def login(
    db: Session,
    email: str,
    password: str,
    *,
    ip: str | None = None,
    user_agent: str | None = None,
    now: datetime | None = None,
) -> LoginResult:
    """Ouvre une session. Lève `AuthenticationError` avec un message unique en cas de refus."""
    settings = get_settings()
    now = _now(now)
    email = normalize_email(email)
    user = auth_repository.get_user_by_email(db, email)

    if user is None:
        security.verify_password(password, None)  # même durée qu'un email existant
        raise _refuse_login(db, email=email, motif="email inconnu", ip=ip)

    if user.verrouille_jusqu_a is not None and user.verrouille_jusqu_a > now:
        security.verify_password(password, None)
        raise _refuse_login(db, email=email, motif="compte verrouillé", user=user, ip=ip)

    if not security.verify_password(password, user.mot_de_passe_hash):
        user.echecs_connexion += 1
        if user.echecs_connexion >= settings.max_login_failures:
            user.verrouille_jusqu_a = now + timedelta(minutes=settings.lockout_minutes)
            user.echecs_connexion = 0  # à l'expiration du verrou, de nouveaux essais sont possibles
            audit_service.log(
                db,
                user_id=user.id,
                action="compte_verrouille",
                entite="user",
                entite_id=user.id,
                apres={"verrouille_jusqu_a": user.verrouille_jusqu_a},
                ip=ip,
            )
        raise _refuse_login(db, email=email, motif="mot de passe incorrect", user=user, ip=ip)

    if not user.actif:
        raise _refuse_login(db, email=email, motif="compte désactivé", user=user, ip=ip)

    user.echecs_connexion = 0
    user.verrouille_jusqu_a = None
    user.dernier_login = now

    session_token = security.new_session_token()
    session = auth_repository.add_session(
        db,
        UserSession(
            user_id=user.id,
            token_hash=security.hash_session_token(session_token),
            expires_at=now + timedelta(hours=settings.session_hours),
            ip=ip,
            user_agent=(user_agent or "")[:255] or None,
        ),
    )
    audit_service.log(
        db,
        user_id=user.id,
        action="connexion",
        entite="user_session",
        entite_id=session.id,
        apres={"expire_le": session.expires_at},
        ip=ip,
    )
    result = _auth_result(db, user, session.id, now)
    db.commit()
    return LoginResult(
        access_token=result.access_token,
        expires_in=result.expires_in,
        user=result.user,
        session_token=session_token,
        session_expires_at=session.expires_at,
    )


def _valid_session(db: Session, session_token: str | None, now: datetime) -> UserSession | None:
    if not session_token:
        return None
    session = auth_repository.get_session_by_hash(db, security.hash_session_token(session_token))
    if session is None or session.revoked_at is not None or session.expires_at <= now:
        return None
    return session


def refresh(db: Session, session_token: str | None, *, now: datetime | None = None) -> AuthResult:
    """Nouveau jeton d'accès à partir du cookie de session. Non audité : il a lieu toutes les 15 min."""
    now = _now(now)
    session = _valid_session(db, session_token, now)
    if session is None or not session.user.actif:
        raise AuthenticationError(SESSION_EXPIRED_MESSAGE)
    return _auth_result(db, session.user, session.id, now)


def logout(
    db: Session, session_token: str | None, *, ip: str | None = None, now: datetime | None = None
) -> None:
    """Révoque la session. Sans effet (et sans erreur) si elle est déjà fermée ou inconnue."""
    now = _now(now)
    session = _valid_session(db, session_token, now)
    if session is None:
        return
    session.revoked_at = now
    audit_service.log(
        db,
        user_id=session.user_id,
        action="deconnexion",
        entite="user_session",
        entite_id=session.id,
        ip=ip,
    )
    db.commit()


def load_current_user(
    db: Session, user_id: int, session_id: int, *, now: datetime | None = None
) -> CurrentUser | None:
    """Utilisateur d'un jeton d'accès, ou None si le compte est désactivé ou la session fermée."""
    user = auth_repository.get_active_session_user(db, user_id, session_id, _now(now))
    if user is None:
        return None
    return _current_user(db, user, session_id)


# --- Gestion des comptes (commande en ligne en attendant l'écran d'administration de P16) ---------


def generate_password() -> str:
    """Mot de passe aléatoire de 20 caractères."""
    return secrets.token_urlsafe(15)


def _check_password_strength(password: str) -> None:
    if len(password) < security.MIN_PASSWORD_LENGTH:
        raise AccountError(
            f"Le mot de passe doit contenir au moins {security.MIN_PASSWORD_LENGTH} caractères."
        )


def create_user(
    db: Session,
    *,
    email: str,
    nom: str,
    role_codes: list[str],
    password: str,
    acteur_id: int | None = None,
) -> User:
    """Crée un compte actif avec ses rôles. Le mot de passe n'est conservé que sous forme hachée."""
    email = normalize_email(email)
    if not email or "@" not in email:
        raise AccountError("Adresse email invalide.")
    if not nom.strip():
        raise AccountError("Le nom est obligatoire.")
    _check_password_strength(password)
    if auth_repository.get_user_by_email(db, email) is not None:
        raise AccountError(f"Un compte existe déjà pour {email}.")

    roles = auth_repository.get_roles_by_codes(db, role_codes)
    unknown = sorted(set(role_codes) - {role.code for role in roles})
    if not role_codes or unknown:
        raise AccountError(f"Rôle inconnu : {', '.join(unknown) or '(aucun)'}.")

    user = auth_repository.add_user(
        db,
        User(
            email=email,
            nom=nom.strip(),
            mot_de_passe_hash=security.hash_password(password),
            roles=roles,
        ),
    )
    audit_service.log(
        db,
        user_id=acteur_id,
        action="creation_utilisateur",
        entite="user",
        entite_id=user.id,
        apres={"email": email, "nom": user.nom, "roles": sorted(role.code for role in roles)},
    )
    db.commit()
    return user


def set_password(
    db: Session,
    *,
    email: str,
    password: str,
    acteur_id: int | None = None,
    now: datetime | None = None,
) -> User:
    """Change le mot de passe, lève le verrouillage et ferme toutes les sessions ouvertes."""
    now = _now(now)
    _check_password_strength(password)
    user = auth_repository.get_user_by_email(db, normalize_email(email))
    if user is None:
        raise AccountError(f"Aucun compte pour {normalize_email(email)}.")

    user.mot_de_passe_hash = security.hash_password(password)
    user.echecs_connexion = 0
    user.verrouille_jusqu_a = None
    revoked = auth_repository.revoke_user_sessions(db, user.id, now)
    audit_service.log(
        db,
        user_id=acteur_id,
        action="modification_mot_de_passe",
        entite="user",
        entite_id=user.id,
        apres={"email": user.email, "sessions_fermees": revoked},
    )
    db.commit()
    return user
