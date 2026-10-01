"""Listes de référence : sociétés et devises."""

from sqlalchemy import select

from app.models import Company
from tests.helpers import bearer, login, make_auth_user


def test_companies_for_any_connected_user(client, reference):
    make_auth_user(reference, "DIRECTION", email="direction@example.com")
    token = login(client, "direction@example.com")

    response = client.get("/api/companies", headers=bearer(token))

    assert response.status_code == 200
    assert [(item["code"], item["nom"]) for item in response.json()] == [
        ("SIMTIS", "Simtis"),
        ("SOCX", "Société X"),
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
