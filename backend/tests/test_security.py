"""Briques de sécurité : hachage, jetons, configuration de production."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import ValidationError

from app.core import security
from app.core.config import DEV_JWT_SECRET, Settings, get_settings
from app.core.security import InvalidTokenError

# --- Mots de passe -------------------------------------------------------------------------------


def test_password_is_hashed_with_argon2id_and_verifies():
    hashed = security.hash_password("un-mot-de-passe-solide")

    assert hashed.startswith("$argon2id$")
    assert "un-mot-de-passe-solide" not in hashed
    assert security.verify_password("un-mot-de-passe-solide", hashed)


def test_wrong_password_is_rejected():
    hashed = security.hash_password("un-mot-de-passe-solide")

    assert not security.verify_password("un-autre-mot-de-passe", hashed)


def test_same_password_gives_different_hashes():
    """Sel aléatoire : deux comptes avec le même mot de passe n'ont pas la même empreinte."""
    assert security.hash_password("identique-123456") != security.hash_password("identique-123456")


def test_missing_or_unreadable_hash_is_rejected_without_error():
    assert not security.verify_password("peu-importe", None)
    assert not security.verify_password("peu-importe", "pas-une-empreinte")


# --- Jeton d'accès -------------------------------------------------------------------------------


def test_access_token_round_trip():
    token = security.create_access_token(42, 7)

    claims = security.decode_access_token(token)

    assert (claims.user_id, claims.session_id) == (42, 7)


def test_access_token_contains_no_permissions():
    """Les droits sont relus en base à chaque requête : un jeton ne doit jamais en transporter."""
    payload = jwt.decode(security.create_access_token(1, 1), options={"verify_signature": False})

    assert set(payload) == {"sub", "sid", "type", "iat", "exp"}


def test_expired_access_token_is_rejected():
    issued = datetime.now(UTC) - timedelta(minutes=get_settings().access_token_minutes + 1)
    token = security.create_access_token(1, 1, now=issued)

    with pytest.raises(InvalidTokenError):
        security.decode_access_token(token)


def test_token_signed_with_another_secret_is_rejected():
    forged = jwt.encode(
        {"sub": "1", "sid": 1, "type": "access", "exp": datetime.now(UTC) + timedelta(minutes=5)},
        "un-autre-secret-de-plus-de-32-caracteres!!",
        algorithm="HS256",
    )

    with pytest.raises(InvalidTokenError):
        security.decode_access_token(forged)


def test_unsigned_token_is_rejected():
    """Attaque classique : un jeton « alg: none » sans signature."""
    unsigned = jwt.encode(
        {"sub": "1", "sid": 1, "type": "access", "exp": datetime.now(UTC) + timedelta(minutes=5)},
        None,
        algorithm="none",
    )

    with pytest.raises(InvalidTokenError):
        security.decode_access_token(unsigned)


@pytest.mark.parametrize(
    "payload",
    [
        {"sub": "1", "sid": 1, "type": "refresh"},  # mauvais type
        {"sub": "1", "type": "access"},  # sans session
        {"sid": 1, "type": "access"},  # sans utilisateur
        {"sub": "abc", "sid": 1, "type": "access"},  # utilisateur non numérique
    ],
)
def test_malformed_access_token_is_rejected(payload):
    payload["exp"] = datetime.now(UTC) + timedelta(minutes=5)
    token = jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")

    with pytest.raises(InvalidTokenError):
        security.decode_access_token(token)


def test_garbage_is_rejected():
    with pytest.raises(InvalidTokenError):
        security.decode_access_token("pas.un.jeton")


# --- Jeton de session ----------------------------------------------------------------------------


def test_session_tokens_are_random_and_long():
    tokens = {security.new_session_token() for _ in range(50)}

    assert len(tokens) == 50
    assert all(len(token) >= 60 for token in tokens)


def test_session_token_hash_is_stable_and_never_the_token():
    token = security.new_session_token()

    assert security.hash_session_token(token) == security.hash_session_token(token)
    assert len(security.hash_session_token(token)) == 64
    assert token not in security.hash_session_token(token)


# --- Configuration -------------------------------------------------------------------------------


def test_development_accepts_the_dev_secret():
    assert Settings(app_env="development", jwt_secret=DEV_JWT_SECRET).jwt_secret == DEV_JWT_SECRET


def test_production_refuses_the_dev_secret():
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(app_env="production", jwt_secret=DEV_JWT_SECRET)


def test_production_refuses_a_short_secret():
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(app_env="production", jwt_secret="trop-court")


def test_production_accepts_a_long_secret():
    assert Settings(app_env="production", jwt_secret="x" * 32).is_production
