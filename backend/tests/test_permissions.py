"""Contrôle d'accès : 401 sans jeton, 403 sans permission, et aucune route oubliée."""

import re
from collections.abc import Iterator

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import require_permission
from app.core.db import get_db
from app.core.permissions import PermissionCode
from app.main import app
from app.models import Permission, Role
from tests.helpers import bearer, login, make_auth_user

# Les seules routes accessibles sans être connecté. En ajouter une ici doit être une décision consciente.
PUBLIC_ROUTES = {
    ("get", "/api/health"),
    ("post", "/api/auth/login"),
    ("post", "/api/auth/refresh"),
    ("post", "/api/auth/logout"),
}


def all_api_operations() -> list[tuple[str, str, dict]]:
    """Toutes les opérations exposées, lues dans le schéma OpenAPI (interface publique de FastAPI)."""
    return [
        (method, path, operation)
        for path, operations in app.openapi()["paths"].items()
        for method, operation in operations.items()
    ]


def test_public_routes_list_is_up_to_date():
    exposed = {(method, path) for method, path, _ in all_api_operations()}

    assert PUBLIC_ROUTES <= exposed, "une route publique déclarée ici n'existe plus"


def test_every_non_public_route_declares_the_bearer_token():
    unprotected = [
        f"{method.upper()} {path}"
        for method, path, operation in all_api_operations()
        if (method, path) not in PUBLIC_ROUTES and not operation.get("security")
    ]

    assert unprotected == [], f"routes sans authentification : {unprotected}"


def test_every_non_public_route_answers_401_without_a_token(client):
    """Filet de sécurité : toute nouvelle route doit refuser un appel anonyme."""
    reached = []
    for method, path, _ in all_api_operations():
        if (method, path) in PUBLIC_ROUTES:
            continue
        url = re.sub(r"\{[^}]+\}", "1", path)  # paramètres de chemin remplacés par 1
        response = client.request(method.upper(), url)
        if response.status_code != 401:
            reached.append(f"{method.upper()} {path} -> {response.status_code}")

    assert reached == []


@pytest.mark.parametrize(
    "authorization",
    ["", "Bearer", "Bearer pas-un-jeton", "Basic dXNlcjpwYXNz", "bearer "],
)
def test_malformed_authorization_header_gives_401(client, authorization):
    response = client.get("/api/auth/me", headers={"Authorization": authorization})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


# --- 403 : permission absente --------------------------------------------------------------------


@pytest.fixture
def guarded_client(db) -> Iterator[TestClient]:
    """Petite application de test avec une route qui exige `banks.manage`."""
    guarded = FastAPI()

    @guarded.get("/protege")
    def protege(user=Depends(require_permission(PermissionCode.BANKS_MANAGE))):
        return {"utilisateur": user.email}

    def test_db():
        yield db

    guarded.dependency_overrides[get_db] = test_db
    with TestClient(guarded) as test_client:
        yield test_client


def test_user_with_the_permission_gets_200(client, guarded_client, reference):
    make_auth_user(reference, "TRESORERIE", email="tresorerie@example.com")
    token = login(client, "tresorerie@example.com")

    response = guarded_client.get("/protege", headers=bearer(token))

    assert response.status_code == 200
    assert response.json() == {"utilisateur": "tresorerie@example.com"}


def test_user_without_the_permission_gets_403(client, guarded_client, reference):
    make_auth_user(reference, "DIRECTION", email="direction@example.com")
    token = login(client, "direction@example.com")

    response = guarded_client.get("/protege", headers=bearer(token))

    assert response.status_code == 403
    assert response.json() == {"detail": "Permission requise : banks.manage."}


def test_anonymous_call_to_a_guarded_route_gets_401_not_403(guarded_client):
    assert guarded_client.get("/protege").status_code == 401


def test_removing_a_permission_applies_on_the_next_request(client, guarded_client, reference, db):
    """Exigence P16 : un changement de droits s'applique sans redéploiement ni reconnexion."""
    make_auth_user(reference, "TRESORERIE", email="tresorerie@example.com")
    token = login(client, "tresorerie@example.com")
    assert guarded_client.get("/protege", headers=bearer(token)).status_code == 200

    role = db.scalar(select(Role).filter_by(code="TRESORERIE"))
    banks_manage = db.scalar(select(Permission).filter_by(code="banks.manage"))
    role.permissions.remove(banks_manage)
    db.flush()

    assert guarded_client.get("/protege", headers=bearer(token)).status_code == 403


def test_permissions_of_several_roles_add_up(client, reference):
    make_auth_user(reference, "DIRECTION", "COMPTABLE", email="cumul@example.com")
    token = login(client, "cumul@example.com")

    permissions = set(client.get("/api/auth/me", headers=bearer(token)).json()["permissions"])

    assert {"dashboard.view", "accounting.import", "reconciliation.validate"} <= permissions
    assert "banks.manage" not in permissions


def test_user_without_any_role_has_no_permission(client, reference):
    make_auth_user(reference, email="sans-role@example.com")
    token = login(client, "sans-role@example.com")

    me = client.get("/api/auth/me", headers=bearer(token)).json()

    assert me["roles"] == []
    assert me["permissions"] == []


def test_permission_codes_in_database_match_the_code(reference):
    in_database = set(reference.scalars(select(Permission.code)))

    assert in_database == {code.value for code in PermissionCode}
