"""Connexion, rafraîchissement, déconnexion et verrouillage, à travers l'API HTTP."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.models import AuditLog, UserSession
from app.services.auth_service import LOGIN_FAILED_MESSAGE
from tests.helpers import TEST_PASSWORD, bearer, login, make_auth_user

LOGIN = "/api/auth/login"
REFRESH = "/api/auth/refresh"
LOGOUT = "/api/auth/logout"
ME = "/api/auth/me"


@pytest.fixture
def user(reference):
    return make_auth_user(reference, "TRESORERIE", email="salma@example.com", nom="Salma")


def audit_actions(db, user_id=None) -> list[str]:
    query = select(AuditLog.action).order_by(AuditLog.id)
    if user_id is not None:
        query = query.where(AuditLog.user_id == user_id)
    return list(db.scalars(query))


def set_cookie_header(response) -> str:
    return response.headers.get("set-cookie", "")


# --- Connexion -----------------------------------------------------------------------------------


def test_login_returns_an_access_token_and_the_user(client, user):
    response = client.post(LOGIN, json={"email": "salma@example.com", "password": TEST_PASSWORD})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == get_settings().access_token_minutes * 60
    assert decode_access_token(body["access_token"]).user_id == user.id
    assert body["user"]["nom"] == "Salma"
    assert body["user"]["roles"] == ["Trésorerie"]
    assert "banks.manage" in body["user"]["permissions"]
    assert "admin.users" not in body["user"]["permissions"]


def test_session_cookie_is_httponly_strict_and_limited_to_auth_routes(client, user):
    response = client.post(LOGIN, json={"email": "salma@example.com", "password": TEST_PASSWORD})

    cookie = set_cookie_header(response)
    assert cookie.startswith("simtis_session=")
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "Path=/api/auth" in cookie
    assert "Secure" not in cookie  # en développement (http)


def test_session_cookie_is_secure_in_production(client, user, production_env):
    response = client.post(LOGIN, json={"email": "salma@example.com", "password": TEST_PASSWORD})

    assert "Secure" in set_cookie_header(response)


def test_email_is_case_and_space_insensitive(client, user):
    response = client.post(LOGIN, json={"email": "  SALMA@Example.COM ", "password": TEST_PASSWORD})

    assert response.status_code == 200


def test_wrong_password_and_unknown_email_get_the_same_answer(client, user):
    wrong_password = client.post(LOGIN, json={"email": "salma@example.com", "password": "faux"})
    unknown_email = client.post(LOGIN, json={"email": "inconnu@example.com", "password": "faux"})

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json() == {"detail": LOGIN_FAILED_MESSAGE}


def test_disabled_account_cannot_log_in_even_with_the_right_password(client, reference):
    make_auth_user(reference, "TRESORERIE", email="parti@example.com", actif=False)

    response = client.post(LOGIN, json={"email": "parti@example.com", "password": TEST_PASSWORD})

    assert response.status_code == 401
    assert response.json() == {"detail": LOGIN_FAILED_MESSAGE}


def test_successful_login_records_last_login(client, user, db):
    login(client, "salma@example.com")
    db.refresh(user)

    assert user.dernier_login is not None


# --- Verrouillage --------------------------------------------------------------------------------


def fail(client, times: int, email: str = "salma@example.com") -> None:
    for _ in range(times):
        response = client.post(LOGIN, json={"email": email, "password": "mauvais"})
        assert response.status_code == 401


def test_account_is_locked_after_too_many_failures(client, user, db):
    fail(client, get_settings().max_login_failures)

    # Même avec le bon mot de passe : refusé, avec le message habituel (rien n'est révélé)
    response = client.post(LOGIN, json={"email": "salma@example.com", "password": TEST_PASSWORD})

    assert response.status_code == 401
    assert response.json() == {"detail": LOGIN_FAILED_MESSAGE}
    db.refresh(user)
    assert user.verrouille_jusqu_a is not None
    assert "compte_verrouille" in audit_actions(db, user.id)


def test_account_unlocks_once_the_delay_has_passed(client, user, db):
    fail(client, get_settings().max_login_failures)
    user.verrouille_jusqu_a = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()

    login(client, "salma@example.com")

    db.refresh(user)
    assert user.verrouille_jusqu_a is None
    assert user.echecs_connexion == 0


def test_a_successful_login_resets_the_failure_counter(client, user, db):
    fail(client, get_settings().max_login_failures - 1)
    login(client, "salma@example.com")
    fail(client, get_settings().max_login_failures - 1)

    db.refresh(user)
    assert user.verrouille_jusqu_a is None


# --- Session : /me, rafraîchissement, déconnexion ------------------------------------------------


def test_me_returns_the_connected_user(client, user):
    token = login(client, "salma@example.com")

    response = client.get(ME, headers=bearer(token))

    assert response.status_code == 200
    assert response.json()["email"] == "salma@example.com"


def test_refresh_with_the_session_cookie_gives_a_working_token(client, user):
    login(client, "salma@example.com")

    response = client.post(REFRESH)

    assert response.status_code == 200
    new_token = response.json()["access_token"]
    assert client.get(ME, headers=bearer(new_token)).status_code == 200


def test_refresh_without_cookie_is_refused(client, user):
    assert client.post(REFRESH).status_code == 401


def test_refresh_with_an_unknown_cookie_is_refused_and_clears_it(client, user):
    client.cookies.set("simtis_session", "jeton-invente", path="/api/auth")

    response = client.post(REFRESH)

    assert response.status_code == 401
    assert "Max-Age=0" in set_cookie_header(response)


def test_refresh_after_the_session_has_expired_is_refused(client, user, db):
    login(client, "salma@example.com")
    session = db.scalar(select(UserSession).where(UserSession.user_id == user.id))
    session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()

    assert client.post(REFRESH).status_code == 401


def test_refresh_is_not_written_to_the_audit_log(client, user, db):
    login(client, "salma@example.com")
    before = len(audit_actions(db))

    client.post(REFRESH)
    client.post(REFRESH)

    assert len(audit_actions(db)) == before


def test_logout_closes_the_session_immediately(client, user):
    token = login(client, "salma@example.com")

    response = client.post(LOGOUT)

    assert response.status_code == 204
    assert "Max-Age=0" in set_cookie_header(response)
    # Le jeton d'accès, pourtant non expiré, ne sert plus à rien
    assert client.get(ME, headers=bearer(token)).status_code == 401
    assert client.post(REFRESH).status_code == 401


def test_logout_twice_is_harmless(client, user):
    login(client, "salma@example.com")

    assert client.post(LOGOUT).status_code == 204
    assert client.post(LOGOUT).status_code == 204


def test_disabling_an_account_cuts_its_access_immediately(client, user, db):
    token = login(client, "salma@example.com")
    user.actif = False
    db.flush()

    assert client.get(ME, headers=bearer(token)).status_code == 401
    assert client.post(REFRESH).status_code == 401


# --- Journal d'audit -----------------------------------------------------------------------------


def test_login_failures_and_logout_are_audited(client, user, db):
    client.post(LOGIN, json={"email": "salma@example.com", "password": "mauvais"})
    client.post(LOGIN, json={"email": "inconnu@example.com", "password": "mauvais"})
    login(client, "salma@example.com")
    client.post(LOGOUT)

    entries = list(db.scalars(select(AuditLog).order_by(AuditLog.id)))
    actions = [(entry.action, (entry.nouvelle_valeur or {}).get("motif")) for entry in entries]

    assert actions == [
        ("echec_connexion", "mot de passe incorrect"),
        ("echec_connexion", "email inconnu"),
        ("connexion", None),
        ("deconnexion", None),
    ]
    assert entries[0].user_id == user.id
    assert entries[1].user_id is None
    assert all(entry.ip for entry in entries)


def test_passwords_never_reach_the_audit_log(client, user, db):
    client.post(LOGIN, json={"email": "salma@example.com", "password": "mauvais-mot-secret"})
    login(client, "salma@example.com")

    everything = " ".join(
        f"{entry.ancienne_valeur} {entry.nouvelle_valeur}" for entry in db.scalars(select(AuditLog))
    )

    assert "mauvais-mot-secret" not in everything
    assert TEST_PASSWORD not in everything
