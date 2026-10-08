"""Listes de référence : sociétés, devises et types de pointage."""

from sqlalchemy import select

from app.models import Company, PointageType
from tests.helpers import bearer, login, make_auth_user


def test_companies_for_any_connected_user(client, reference):
    make_auth_user(reference, "DIRECTION", email="direction@example.com")
    token = login(client, "direction@example.com")

    response = client.get("/api/companies", headers=bearer(token))

    assert response.status_code == 200
    assert [(item["code"], item["nom"]) for item in response.json()] == [
        ("SIMTIS", "Simtis"),
        ("SOCX", "Tefil"),
    ]


def test_inactive_company_is_not_listed(client, reference):
    reference.scalar(select(Company).filter_by(code="SOCX")).actif = False
    reference.flush()
    make_auth_user(reference, email="sans-role@example.com")
    token = login(client, "sans-role@example.com")

    codes = [item["code"] for item in client.get("/api/companies", headers=bearer(token)).json()]

    assert codes == ["SIMTIS"]


def test_currencies_list_mad_first(client, reference):
    make_auth_user(reference, email="sans-role@example.com")
    token = login(client, "sans-role@example.com")

    response = client.get("/api/currencies", headers=bearer(token))

    assert [item["code"] for item in response.json()] == ["MAD", "EUR", "USD"]


def test_reference_lists_require_a_login(client, reference):
    assert client.get("/api/companies").status_code == 401
    assert client.get("/api/currencies").status_code == 401


# --- Types de pointage ------------------------------------------------------------------------------


def test_pointage_types_are_listed_for_any_logged_in_user(client, reference):
    make_auth_user(reference, "DIRECTION", email="direction.pointage@example.com")
    headers = bearer(login(client, "direction.pointage@example.com"))

    response = client.get("/api/pointage-types", headers=headers)

    assert response.status_code == 200
    libelles = [item["libelle"] for item in response.json()]
    # Les 74 catégories du métier (08/10/2026), par ordre alphabétique sans casse ni accents
    assert len(libelles) == 74
    assert libelles[:3] == ["A NOUVEAU", "A voir", "AGIOS"]
    assert libelles.index("Cheque de banque") < libelles.index("CHEQUE SOFT")
    assert not {"Encaissement", "Décaissement", "Frais bancaires"} & set(libelles)
    assert set(response.json()[0]) == {"id", "code", "libelle"}


def test_inactive_pointage_types_are_not_listed(client, reference, db):
    frais = db.scalar(select(PointageType).filter_by(code="FRAIS"))
    frais.actif = False
    db.flush()
    make_auth_user(reference, "DIRECTION", email="direction.pointage2@example.com")

    body = client.get(
        "/api/pointage-types", headers=bearer(login(client, "direction.pointage2@example.com"))
    ).json()

    assert "FRAIS" not in {item["code"] for item in body}


def test_pointage_types_need_a_login(client):
    assert client.get("/api/pointage-types").status_code == 401
