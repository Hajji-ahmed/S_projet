"""Gestion des sociétés par l'administrateur (17/11/2026) : création, renommage, activation."""

import pytest
from sqlalchemy import select

from app.models import AuditLog, Company
from tests.helpers import bearer, login, make_auth_user

COMPANIES = "/api/companies"


@pytest.fixture
def admin(client, reference) -> dict[str, str]:
    make_auth_user(reference, "ADMIN", email="admin.societes@example.com")
    return bearer(login(client, "admin.societes@example.com"))


@pytest.fixture
def tresorerie(client, reference) -> dict[str, str]:
    make_auth_user(reference, "TRESORERIE", email="tresorerie.societes@example.com")
    return bearer(login(client, "tresorerie.societes@example.com"))


def company(db, code: str) -> Company:
    return db.scalar(select(Company).filter_by(code=code))


def audit_entries(db, action: str) -> list[AuditLog]:
    return list(db.scalars(select(AuditLog).filter_by(action=action).order_by(AuditLog.id)))


# --- Création ------------------------------------------------------------------------------------


def test_admin_creates_a_company(client, admin, db):
    response = client.post(
        COMPANIES, json={"code": " atlas ", "nom": "  Société   Atlas "}, headers=admin
    )

    assert response.status_code == 201
    body = response.json()
    assert body == {"id": body["id"], "code": "ATLAS", "nom": "Société Atlas", "actif": True}
    codes = [item["code"] for item in client.get(COMPANIES, headers=admin).json()]
    assert codes == ["SIMTIS", "SOCX", "ATLAS"]
    (entry,) = audit_entries(db, "creation_societe")
    assert entry.entite == "company"
    assert entry.entite_id == str(body["id"])
    assert entry.nouvelle_valeur == {"code": "ATLAS", "nom": "Société Atlas", "actif": True}


def test_code_already_used_is_refused(client, admin):
    response = client.post(COMPANIES, json={"code": "socx", "nom": "Autre"}, headers=admin)

    assert response.status_code == 409
    assert "SOCX" in response.json()["detail"]


def test_nom_already_used_is_refused_whatever_the_case(client, admin):
    response = client.post(COMPANIES, json={"code": "TEF2", "nom": "TEFIL"}, headers=admin)

    assert response.status_code == 409
    assert "Tefil" in response.json()["detail"]


@pytest.mark.parametrize(
    "payload",
    [
        {"code": "A", "nom": "Atlas"},
        {"code": "AT LAS", "nom": "Atlas"},
        {"code": "X" * 21, "nom": "Atlas"},
        {"code": "ATLAS", "nom": "   "},
        {"code": "ATLAS", "nom": "Atlas", "actif": False},
    ],
)
def test_invalid_creation_is_rejected(client, admin, payload):
    assert client.post(COMPANIES, json=payload, headers=admin).status_code == 422


# --- Modification --------------------------------------------------------------------------------


def test_admin_renames_a_company(client, admin, db):
    socx = company(db, "SOCX")

    response = client.patch(f"{COMPANIES}/{socx.id}", json={"nom": "Tefil SA"}, headers=admin)

    assert response.status_code == 200
    assert response.json()["nom"] == "Tefil SA"
    assert response.json()["code"] == "SOCX"
    (entry,) = audit_entries(db, "modification_societe")
    assert (entry.ancienne_valeur, entry.nouvelle_valeur) == ({"nom": "Tefil"}, {"nom": "Tefil SA"})


def test_renaming_to_the_same_name_writes_nothing(client, admin, db):
    socx = company(db, "SOCX")

    response = client.patch(f"{COMPANIES}/{socx.id}", json={"nom": "Tefil"}, headers=admin)

    assert response.status_code == 200
    assert audit_entries(db, "modification_societe") == []


def test_renaming_to_another_company_name_is_refused(client, admin, db):
    socx = company(db, "SOCX")

    response = client.patch(f"{COMPANIES}/{socx.id}", json={"nom": "simtis"}, headers=admin)

    assert response.status_code == 409


def test_code_cannot_be_changed(client, admin, db):
    socx = company(db, "SOCX")

    response = client.patch(f"{COMPANIES}/{socx.id}", json={"code": "TEFIL"}, headers=admin)

    assert response.status_code == 422
    assert company(db, "SOCX") is not None


def test_unknown_company_gives_404(client, admin):
    assert client.patch(f"{COMPANIES}/999999", json={"nom": "X"}, headers=admin).status_code == 404


# --- Activation ----------------------------------------------------------------------------------


def test_deactivated_company_leaves_the_selector_but_stays_in_the_full_list(client, admin, db):
    socx = company(db, "SOCX")

    response = client.patch(f"{COMPANIES}/{socx.id}", json={"actif": False}, headers=admin)

    assert response.status_code == 200
    assert response.json()["actif"] is False
    assert [item["code"] for item in client.get(COMPANIES, headers=admin).json()] == ["SIMTIS"]
    toutes = client.get(f"{COMPANIES}/toutes", headers=admin).json()
    assert [(item["code"], item["actif"]) for item in toutes] == [
        ("SIMTIS", True),
        ("SOCX", False),
    ]
    (entry,) = audit_entries(db, "desactivation_societe")
    assert (entry.ancienne_valeur, entry.nouvelle_valeur) == ({"actif": True}, {"actif": False})


def test_reactivation(client, admin, db):
    socx = company(db, "SOCX")
    client.patch(f"{COMPANIES}/{socx.id}", json={"actif": False}, headers=admin)

    response = client.patch(f"{COMPANIES}/{socx.id}", json={"actif": True}, headers=admin)

    assert response.json()["actif"] is True
    assert len(audit_entries(db, "reactivation_societe")) == 1


def test_last_active_company_cannot_be_deactivated(client, admin, db):
    simtis, socx = company(db, "SIMTIS"), company(db, "SOCX")
    client.patch(f"{COMPANIES}/{socx.id}", json={"actif": False}, headers=admin)

    response = client.patch(
        f"{COMPANIES}/{simtis.id}", json={"nom": "Simtis SA", "actif": False}, headers=admin
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Il doit rester au moins une société active."
    db.expire_all()
    # Rien n'a changé : les règles sont vérifiées avant toute modification
    assert (company(db, "SIMTIS").nom, company(db, "SIMTIS").actif) == ("Simtis", True)


# --- Droits --------------------------------------------------------------------------------------


def test_management_requires_admin_settings(client, tresorerie, db):
    socx = company(db, "SOCX")

    assert client.get(f"{COMPANIES}/toutes", headers=tresorerie).status_code == 403
    assert (
        client.post(
            COMPANIES, json={"code": "ATLAS", "nom": "Atlas"}, headers=tresorerie
        ).status_code
        == 403
    )
    assert (
        client.patch(f"{COMPANIES}/{socx.id}", json={"nom": "X"}, headers=tresorerie).status_code
        == 403
    )
    # La liste du sélecteur reste ouverte à tout utilisateur connecté
    assert client.get(COMPANIES, headers=tresorerie).status_code == 200


def test_management_requires_a_login(client, reference):
    assert client.get(f"{COMPANIES}/toutes").status_code == 401
    assert client.post(COMPANIES, json={"code": "ATLAS", "nom": "Atlas"}).status_code == 401
    assert client.patch(f"{COMPANIES}/1", json={"nom": "X"}).status_code == 401
