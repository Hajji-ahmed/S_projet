"""Administration (P16.1) : utilisateurs, rôles, permissions, garde-fous et audit."""

import pytest
from sqlalchemy import select

from app.core.permissions import PermissionCode
from app.models import AuditLog, Role, User
from app.services.admin_service import code_role
from tests.helpers import bearer, login, make_auth_user


@pytest.fixture
def admin(client, reference):
    user = make_auth_user(reference, "ADMIN", email="admin@example.com")
    return user, bearer(login(client, "admin@example.com"))


def role_id(db, code: str) -> int:
    return db.scalar(select(Role.id).where(Role.code == code))


def audits(db, action: str) -> list[AuditLog]:
    return list(db.scalars(select(AuditLog).where(AuditLog.action == action)))


# --- Utilisateurs ---------------------------------------------------------------------------------


def test_an_admin_creates_a_user_who_can_log_in_with_the_one_time_password(client, admin, db):
    _, headers = admin

    response = client.post(
        "/api/admin/users",
        json={
            "nom": "  Salma   Idrissi ",
            "email": "Salma@Example.com",
            "role_ids": [role_id(db, "TRESORERIE")],
        },
        headers=headers,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user"]["nom"] == "Salma Idrissi"
    assert body["user"]["email"] == "salma@example.com"
    assert [r["code"] for r in body["user"]["roles"]] == ["TRESORERIE"]
    assert len(body["mot_de_passe"]) >= 12
    login(client, "salma@example.com", body["mot_de_passe"])
    [audit] = audits(db, "creation_utilisateur")
    assert "mot_de_passe" not in str(audit.nouvelle_valeur)
    # La liste ne renvoie jamais de mot de passe
    listed = client.get("/api/admin/users", headers=headers).json()
    assert "mot_de_passe" not in str(listed)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"nom": "X", "email": "pas-un-email", "role_ids": [1]}, "Adresse email invalide."),
        ({"nom": " ", "email": "x@example.com", "role_ids": [1]}, "Le nom est obligatoire."),
        ({"nom": "X", "email": "x@example.com", "role_ids": []}, "Choisissez au moins un rôle."),
        ({"nom": "X", "email": "admin@example.com", "role_ids": [1]}, "existe déjà"),
    ],
)
def test_user_creation_is_checked(client, admin, payload, message):
    response = client.post("/api/admin/users", json=payload, headers=admin[1])

    assert response.status_code == 409
    assert message in response.json()["detail"]


def test_changing_roles_applies_on_the_next_request(client, admin, db):
    _, headers = admin
    salma = make_auth_user(db, "DIRECTION", email="salma@example.com")
    salma_headers = bearer(login(client, "salma@example.com"))
    assert client.get("/api/admin/users", headers=salma_headers).status_code == 403

    response = client.put(
        f"/api/admin/users/{salma.id}",
        json={"nom": "Salma", "email": "salma@example.com", "role_ids": [role_id(db, "ADMIN")]},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert client.get("/api/admin/users", headers=salma_headers).status_code == 200
    [audit] = audits(db, "modification_utilisateur")
    assert audit.ancienne_valeur["roles"] == ["DIRECTION"]
    assert audit.nouvelle_valeur["roles"] == ["ADMIN"]


def test_deactivating_a_user_cuts_access_at_once(client, admin, db):
    _, headers = admin
    salma = make_auth_user(db, "DIRECTION", email="salma@example.com")
    salma_headers = bearer(login(client, "salma@example.com"))

    response = client.patch(
        f"/api/admin/users/{salma.id}/status", json={"actif": False}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["actif"] is False
    assert client.get("/api/auth/me", headers=salma_headers).status_code == 401
    assert audits(db, "desactivation_utilisateur")[0].nouvelle_valeur["sessions_fermees"] == 1


def test_an_admin_cannot_lock_themselves_out(client, admin, db):
    me, headers = admin

    statut = client.patch(
        f"/api/admin/users/{me.id}/status", json={"actif": False}, headers=headers
    )
    roles = client.put(
        f"/api/admin/users/{me.id}",
        json={"nom": "Moi", "email": me.email, "role_ids": [role_id(db, "DIRECTION")]},
        headers=headers,
    )

    assert statut.status_code == 409
    assert roles.status_code == 409
    assert "propre rôle Administrateur" in roles.json()["detail"]


def test_the_last_active_admin_can_never_be_removed(client, admin, db):
    """Un gestionnaire des comptes (admin.users sans être administrateur) ne peut ni désactiver
    ni rétrograder le seul administrateur actif."""
    me, _ = admin
    direction = db.scalar(select(Role).where(Role.code == "DIRECTION"))
    admin_role = db.scalar(select(Role).where(Role.code == "ADMIN"))
    direction.permissions.append(
        next(p for p in admin_role.permissions if p.code == PermissionCode.ADMIN_USERS)
    )
    make_auth_user(db, "DIRECTION", email="rh@example.com")
    rh = bearer(login(client, "rh@example.com"))

    statut = client.patch(f"/api/admin/users/{me.id}/status", json={"actif": False}, headers=rh)
    roles = client.put(
        f"/api/admin/users/{me.id}",
        json={"nom": "Moi", "email": me.email, "role_ids": [role_id(db, "DIRECTION")]},
        headers=rh,
    )

    for response in (statut, roles):
        assert response.status_code == 409
        assert response.json()["detail"] == "Il doit rester au moins un administrateur actif."
    assert db.get(User, me.id).actif is True


def test_resetting_a_password_unlocks_and_closes_sessions(client, admin, db):
    _, headers = admin
    salma = make_auth_user(db, "DIRECTION", email="salma@example.com", echecs_connexion=5)
    salma_headers = bearer(login(client, "salma@example.com"))

    response = client.post(f"/api/admin/users/{salma.id}/password", headers=headers)

    assert response.status_code == 200
    nouveau = response.json()["mot_de_passe"]
    assert client.get("/api/auth/me", headers=salma_headers).status_code == 401
    login(client, "salma@example.com", nouveau)
    assert db.get(User, salma.id).echecs_connexion == 0
    assert len(audits(db, "reinitialisation_mot_de_passe")) == 1


# --- Rôles et permissions -------------------------------------------------------------------------


def test_a_custom_role_gets_exactly_its_permissions(client, admin, db):
    _, headers = admin

    response = client.post(
        "/api/admin/roles",
        json={
            "nom": "Contrôle de gestion",
            "description": "Lecture seule",
            "permissions": ["dashboard.view", "position.view"],
        },
        headers=headers,
    )

    assert response.status_code == 201, response.text
    role = response.json()
    assert (role["code"], role["systeme"]) == ("PERSO_CONTROLE_DE_GESTION", False)
    assert role["permissions"] == ["dashboard.view", "position.view"]
    make_auth_user(db, "PERSO_CONTROLE_DE_GESTION", email="cg@example.com")
    cg = bearer(login(client, "cg@example.com"))
    assert client.get("/api/auth/me", headers=cg).json()["permissions"] == [
        "dashboard.view",
        "position.view",
    ]


def test_editing_the_matrix_applies_on_the_next_request_and_is_audited(client, admin, db):
    _, headers = admin
    make_auth_user(db, "DIRECTION", email="dir@example.com")
    dir_headers = bearer(login(client, "dir@example.com"))
    direction = client.get("/api/admin/roles", headers=headers).json()
    direction = next(r for r in direction if r["code"] == "DIRECTION")
    assert "audit.view" not in direction["permissions"]

    response = client.put(
        f"/api/admin/roles/{direction['id']}",
        json={
            "nom": "ignoré pour un rôle système",
            "permissions": [*direction["permissions"], "audit.view"],
        },
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["nom"] == "Direction / Consultation"
    me = client.get("/api/auth/me", headers=dir_headers).json()
    assert "audit.view" in me["permissions"]
    [audit] = audits(db, "modification_permissions")
    assert "audit.view" not in audit.ancienne_valeur["permissions"]
    assert "audit.view" in audit.nouvelle_valeur["permissions"]


def test_the_admin_role_keeps_administration(client, admin, db):
    response = client.put(
        f"/api/admin/roles/{role_id(db, 'ADMIN')}",
        json={"nom": "Administrateur", "permissions": ["dashboard.view"]},
        headers=admin[1],
    )

    assert response.status_code == 409


def test_roles_are_deleted_only_when_custom_and_unused(client, admin, db):
    _, headers = admin
    systeme = client.delete(f"/api/admin/roles/{role_id(db, 'DIRECTION')}", headers=headers)
    created = client.post(
        "/api/admin/roles", json={"nom": "Audit externe", "permissions": []}, headers=headers
    ).json()
    make_auth_user(db, "PERSO_AUDIT_EXTERNE", email="ext@example.com")
    utilise = client.delete(f"/api/admin/roles/{created['id']}", headers=headers)

    assert systeme.status_code == 409
    assert utilise.status_code == 409
    assert "attribué à 1 utilisateur" in utilise.json()["detail"]

    libre = client.post(
        "/api/admin/roles", json={"nom": "Temporaire", "permissions": []}, headers=headers
    ).json()
    assert client.delete(f"/api/admin/roles/{libre['id']}", headers=headers).status_code == 204
    assert audits(db, "suppression_role")[0].ancienne_valeur["code"] == "PERSO_TEMPORAIRE"


def test_unknown_permissions_and_duplicate_role_names_are_refused(client, admin):
    _, headers = admin
    inconnue = client.post(
        "/api/admin/roles", json={"nom": "X", "permissions": ["nimporte.quoi"]}, headers=headers
    )
    doublon = client.post(
        "/api/admin/roles", json={"nom": "trésorerie", "permissions": []}, headers=headers
    )

    assert inconnue.status_code == 409
    assert doublon.status_code == 409


def test_permissions_are_listed_by_module(client, admin):
    permissions = client.get("/api/admin/permissions", headers=admin[1]).json()

    assert {p["code"] for p in permissions} == {code.value for code in PermissionCode}
    assert next(p for p in permissions if p["code"] == "audit.view")["module"] == "Historique"


def test_administration_needs_its_permissions(client, reference):
    make_auth_user(reference, "COMPTABLE", email="compta@example.com")
    headers = bearer(login(client, "compta@example.com"))

    assert client.get("/api/admin/users", headers=headers).status_code == 403
    assert client.get("/api/admin/roles", headers=headers).status_code == 403
    assert client.get("/api/admin/permissions", headers=headers).status_code == 403
    assert client.post("/api/admin/roles", json={}, headers=headers).status_code in (403, 422)


@pytest.mark.parametrize(
    ("nom", "code"),
    [
        ("Contrôle de gestion", "PERSO_CONTROLE_DE_GESTION"),
        ("  Audit / externe  ", "PERSO_AUDIT_EXTERNE"),
        ("é" * 3, "PERSO_EEE"),
    ],
)
def test_role_codes_are_derived_from_the_name(nom, code):
    assert code_role(nom) == code


# --- Permissions par personne (23/10/2026) --------------------------------------------------------


@pytest.fixture
def comptable(client, reference):
    user = make_auth_user(reference, "COMPTABLE", email="compta-perso@example.com")
    return user, bearer(login(client, "compta-perso@example.com"))


def _perms(client, headers, user_id):
    return client.get(f"/api/admin/users/{user_id}/permissions", headers=headers)


def _set(client, headers, user_id, ajouts=(), retraits=()):
    return client.put(
        f"/api/admin/users/{user_id}/permissions",
        json={"ajouts": list(ajouts), "retraits": list(retraits)},
        headers=headers,
    )


def test_a_permission_added_to_one_person_applies_at_once(client, admin, comptable, db):
    _, headers = admin
    user, compta = comptable
    assert client.get("/api/audit", headers=compta).status_code == 403

    response = _set(client, headers, user.id, ajouts=["audit.view"])

    assert response.status_code == 200, response.text
    audit_view = next(p for p in response.json() if p["code"] == "audit.view")
    assert (audit_view["personnalisation"], audit_view["effective"]) == (True, True)
    assert client.get("/api/audit", headers=compta).status_code == 200
    assert "audit.view" in client.get("/api/auth/me", headers=compta).json()["permissions"]
    [entry] = audits(db, "modification_permissions_utilisateur")
    assert entry.nouvelle_valeur == {"ajouts": ["audit.view"], "retraits": []}


def test_a_permission_removed_from_one_person_leaves_the_role_untouched(
    client, admin, comptable, db
):
    from app.models import Company

    _, headers = admin
    user, compta = comptable
    company_id = db.scalar(select(Company.id).where(Company.code == "SIMTIS"))
    autre = make_auth_user(db, "COMPTABLE", email="autre-compta@example.com")
    autre_headers = bearer(login(client, "autre-compta@example.com"))

    assert _set(client, headers, user.id, retraits=["dashboard.view"]).status_code == 200

    params = {"company_id": str(company_id)}
    assert client.get("/api/dashboard", params=params, headers=compta).status_code == 403
    assert client.get("/api/dashboard", params=params, headers=autre_headers).status_code == 200
    detail = next(
        p for p in _perms(client, headers, user.id).json() if p["code"] == "dashboard.view"
    )
    assert detail["par_roles"] == ["Comptable"]
    assert (detail["personnalisation"], detail["effective"]) == (False, False)
    [ligne] = [
        u for u in client.get("/api/admin/users", headers=headers).json() if u["id"] == user.id
    ]
    assert (ligne["nb_ajouts"], ligne["nb_retraits"]) == (0, 1)
    assert autre.id != user.id


def test_useless_changes_are_not_stored(client, admin, comptable, db):
    _, headers = admin
    user, _ = comptable

    # Déjà donnée par le rôle Comptable, et pas donnée par lui
    response = _set(client, headers, user.id, ajouts=["accounting.import"], retraits=["audit.view"])

    assert response.status_code == 200
    assert all(p["personnalisation"] is None for p in response.json())
    assert audits(db, "modification_permissions_utilisateur") == []


def test_an_admin_keeps_user_and_role_administration(client, admin, db):
    user, headers = admin

    response = _set(client, headers, user.id, retraits=["admin.users"])

    assert response.status_code == 409
    assert "garde l'administration" in response.json()["detail"]
    locked = {p["code"] for p in _perms(client, headers, user.id).json() if p["verrouillee"]}
    assert locked == {"admin.users", "admin.roles"}


def test_wrong_permission_changes_are_refused(client, admin, comptable):
    _, headers = admin
    user, _ = comptable

    inconnue = _set(client, headers, user.id, ajouts=["inconnue.code"])
    les_deux = _set(client, headers, user.id, ajouts=["audit.view"], retraits=["audit.view"])
    personne = _set(client, headers, 999999, ajouts=["audit.view"])

    assert (inconnue.status_code, les_deux.status_code, personne.status_code) == (409, 409, 404)


def test_personal_permissions_need_user_administration(client, comptable):
    user, compta = comptable

    assert _perms(client, compta, user.id).status_code == 403
    assert _set(client, compta, user.id, ajouts=["audit.view"]).status_code == 403
