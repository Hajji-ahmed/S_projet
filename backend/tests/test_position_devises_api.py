"""Tableau Devises : soldes des comptes EUR / USD (décision du 05/10/2026), GET /api/position/devises/soldes."""

from datetime import date
from decimal import Decimal
from itertools import count

import pytest
from sqlalchemy import select

from app.models import Bank, BankAccount, BankAccountBalance, Company
from tests.helpers import bearer, build_account, login, make_auth_user, save

URL = "/api/position/devises/soldes"
# Dates passées : aucun résultat ne dépend du décalage horaire du Maroc
J29, J30 = date(2025, 9, 29), date(2025, 9, 30)
_numeros = count(1)


@pytest.fixture
def direction(client, reference) -> dict[str, str]:
    make_auth_user(reference, "DIRECTION", email="direction@example.com")
    return bearer(login(client, "direction@example.com"))


def company(db, code: str = "SIMTIS") -> Company:
    return db.scalar(select(Company).filter_by(code=code))


def bank(db, code: str) -> Bank:
    return db.scalar(select(Bank).filter_by(code=code))


def account(db, bank_code: str, devise: str, company_code: str = "SIMTIS", **over) -> BankAccount:
    over.setdefault("numero", f"RIB-DEV-{next(_numeros):06d}")
    return save(
        db, build_account(company(db, company_code), bank(db, bank_code), devise=devise, **over)
    )


def balance(db, compte: BankAccount, jour: date, solde: str) -> None:
    save(db, BankAccountBalance(bank_account_id=compte.id, date_solde=jour, solde=Decimal(solde)))


def get(client, headers, db, jour: date = J30, code: str = "SIMTIS"):
    params = {"company_id": str(company(db, code).id), "date": jour.isoformat()}
    return client.get(URL, params=params, headers=headers)


def line(body: dict, devise: str) -> dict:
    return next(item for item in body["lignes"] if item["devise"] == devise)


def cell(body: dict, devise: str, bank_code: str) -> dict:
    index = [banque["code"] for banque in body["banques"]].index(bank_code)
    return line(body, devise)["cellules"][index]


def test_eur_and_usd_balances_without_conversion(client, direction, db):
    awb, cih = account(db, "AWB", "EUR"), account(db, "CIH", "EUR")
    usd = account(db, "BP", "USD")
    balance(db, awb, J30, "1500.50")
    balance(db, cih, J29, "200")
    balance(db, usd, J30, "75")

    response = get(client, direction, db)

    assert response.status_code == 200
    body = response.json()
    assert body["affiche"] is True
    assert body["date_fin"] == "2025-09-30"
    assert [banque["code"] for banque in body["banques"]] == ["AWB", "BMCE", "BP", "CIH", "BMCI"]
    assert [item["devise"] for item in body["lignes"]] == ["EUR", "USD"]
    assert cell(body, "EUR", "AWB") | {"bank_id": 0} == {
        "bank_id": 0,
        "valeur": "1500.50",
        "date_solde": "2025-09-30",
        "reprise": False,
    }
    assert cell(body, "EUR", "CIH")["reprise"] is True
    assert cell(body, "EUR", "BP")["valeur"] is None
    assert line(body, "EUR")["total"] == "1700.50"
    assert line(body, "USD")["total"] == "75.00"  # jamais additionné aux euros


def test_mad_accounts_and_other_companies_are_ignored(client, direction, db):
    balance(db, account(db, "AWB", "EUR"), J30, "10")
    balance(db, account(db, "BP", "MAD"), J30, "999999")
    balance(db, account(db, "BP", "EUR", company_code="SOCX"), J30, "888888")

    body = get(client, direction, db).json()

    assert line(body, "EUR")["total"] == "10.00"
    assert line(body, "USD")["total"] is None


def test_inactive_currency_account_is_ignored(client, direction, db):
    balance(db, account(db, "AWB", "EUR"), J30, "10")
    balance(db, account(db, "BP", "EUR", actif=False), J30, "5")

    assert line(get(client, direction, db).json(), "EUR")["total"] == "10.00"


def test_company_without_currency_account_has_no_table(client, direction, db):
    account(db, "AWB", "MAD", company_code="SOCX")

    body = get(client, direction, db, code="SOCX").json()

    assert body["affiche"] is False


def test_dh_convertible_account_alone_shows_the_table(client, direction, db):
    """La ligne Exp DH convertible reste saisie à la main : son compte suffit à afficher le tableau."""
    account(db, "AWB", "MAD", company_code="SOCX", type_compte="DH convertible")

    body = get(client, direction, db, code="SOCX").json()

    assert body["affiche"] is True
    assert line(body, "EUR")["total"] is None


def test_unknown_company_gives_404(client, direction):
    response = client.get(URL, params={"company_id": "999999"}, headers=direction)

    assert response.status_code == 404
    assert response.json() == {"detail": "Société introuvable."}


def test_requires_a_token(client, reference):
    assert client.get(URL, params={"company_id": "1"}).status_code == 401


def test_requires_position_view(client, reference, db):
    make_auth_user(reference, email="sans-role@example.com")
    headers = bearer(login(client, "sans-role@example.com"))

    assert get(client, headers, db).status_code == 403
