"""Briques de sécurité : mots de passe, jeton d'accès, jeton de session.

Aucune règle métier ici : ce module ne connaît ni la base ni les utilisateurs.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core.config import get_settings

JWT_ALGORITHM = "HS256"
# Tolérance aux décalages d'horloge : la machine virtuelle de Docker Desktop recale parfois son heure de
# plusieurs dizaines de secondes en arrière, et un jeton tout juste émis paraîtrait « émis dans le futur ».
CLOCK_SKEW_SECONDS = 60
ACCESS_TOKEN_TYPE: Literal["access"] = "access"
MIN_PASSWORD_LENGTH = 12

# argon2id avec les paramètres par défaut de la bibliothèque
_password_hash = PasswordHash((Argon2Hasher(),))

# Haché une fois, sert à occuper le même temps quand l'email est inconnu (voir `verify_password`)
_DUMMY_HASH = _password_hash.hash("mot-de-passe-factice-pour-egaliser-les-temps")


class InvalidTokenError(Exception):
    """Jeton absent, mal formé, falsifié, expiré ou du mauvais type."""


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Compare un mot de passe à son empreinte.

    Avec `password_hash=None` (email inconnu), une vérification factice est faite quand même : le temps
    de réponse ne révèle pas si l'adresse existe.
    """
    if password_hash is None:
        _password_hash.verify(password, _DUMMY_HASH)
        return False
    try:
        return _password_hash.verify(password, password_hash)
    except Exception:  # empreinte illisible : refuser plutôt que planter
        return False


@dataclass(frozen=True)
class AccessClaims:
    user_id: int
    session_id: int


def create_access_token(user_id: int, session_id: int, *, now: datetime | None = None) -> str:
    """Jeton d'accès à courte durée.

    Il ne contient AUCUN droit : les permissions sont relues en base à chaque requête. Il porte
    l'identifiant de sa session, ce qui le rend inutilisable dès que la session est révoquée.
    """
    settings = get_settings()
    issued_at = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "sid": session_id,
        "type": ACCESS_TOKEN_TYPE,
        "iat": issued_at,
        "exp": issued_at + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> AccessClaims:
    """Vérifie signature, expiration et type, ou lève `InvalidTokenError`."""
    try:
        payload = jwt.decode(
            token,
            get_settings().jwt_secret,
            # Liste explicite : on n'accepte jamais l'algorithme annoncé par le jeton lui-même
            algorithms=[JWT_ALGORITHM],
            leeway=CLOCK_SKEW_SECONDS,
            options={"require": ["exp", "sub", "sid", "type"]},
        )
    except jwt.PyJWTError as error:
        raise InvalidTokenError(str(error)) from error

    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise InvalidTokenError("type de jeton inattendu")
    try:
        return AccessClaims(user_id=int(payload["sub"]), session_id=int(payload["sid"]))
    except (TypeError, ValueError) as error:
        raise InvalidTokenError("identifiants du jeton invalides") from error


def new_session_token() -> str:
    """Jeton de session opaque et aléatoire, remis au navigateur dans un cookie HttpOnly."""
    return secrets.token_urlsafe(48)


def hash_session_token(token: str) -> str:
    """Seule cette empreinte est stockée : une fuite de la base ne donne aucune session utilisable."""
    return hashlib.sha256(token.encode()).hexdigest()
