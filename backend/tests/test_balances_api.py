"""Soldes du jour : saisie, correction, historique, et chiffres des comptes et des banques."""

from datetime import date, timedelta
from decimal import Decimal
from itertools import count

import pytest
from sqlalchemy import select

from app.models import AuditLog, Bank, BankAccount, BankAccountBalance, Company
from app.services.position_service import business_today
from tests.helpers import bearer, build_account, login, make_auth_user, save

TODAY = business_today()
_numeros = count(1)


@pytest.fixture
def tresorerie(client, reference) -> dict[str, str]:
    make_auth_user(reference, "TRESORERIE", email="tresorerie@example.com", nom="Salma")
    return bearer(login(client, "tresorerie@example.com"))


@pytest.fixture
def direction(client, reference) -> dict[str, str]:
    make_auth_user(reference, "DIRECTION", email="direction@example.com")
    return bearer(login(client, "direction@example.com"))


def company(db, code: str) -> Company:
    return db.scalar(select(Company).filter_by(code=code))


def add(db, company_code: str, bank_code: str, **over) -> BankAccount:
    over.setdefault("numero", f"RIB-SOLDE-{next(_numeros):06d}")
    bank = db.scalar(select(Bank).filter_by(code=bank_code))
    return save(db, build_account(company(db, company_code), bank, **over))


def url(account: BankAccount, jour=TODAY) -> str:
    return f"/api/accounts/{account.id}/balances/{jour.isoformat()}"


def audit(db, action: str) -> list[AuditLog]:
    return list(db.scalars(select(AuditLog).filter_by(action=action).order_by(AuditLog.id)))


# --- Saisie et correction ------------------------------------------------------------------------


def test_enter_today_balance(client, tresorerie, db):
    account = add(db, "SIMTIS", "CIH")

    response = client.put(
        url(account), json={"solde": "300000", "credit_utilise": "100000.5"}, headers=tresorerie
    )

    assert response.status_code == 200
    assert response.json() | {"id": 0} == {
        "id": 0,
        "date_solde": TODAY.isoformat(),
        "solde": "300000.00",
        "credit_utilise": "100000.50",
        "source": "Saisie",
        "commentaire": None,
        "saisi_par": "Salma",
    }
    [entry] = audit(db, "saisie_solde")
    assert entry.nouvelle_valeur["solde"] == "300000.00"
    assert entry.ancienne_valeur is None


def test_entering_the_same_day_again_corrects_it(client, tresorerie, db):
    account = add(db, "SIMTIS", "CIH")
    client.put(
        url(account), json={"solde": "300000", "credit_utilise": "100000"}, headers=tresorerie
    )

    client.put(
        url(account), json={"solde": "310000", "credit_utilise": "100000"}, headers=tresorerie
    )

    rows = db.scalars(select(BankAccountBalance).filter_by(bank_account_id=account.id)).all()
    assert len(rows) == 1 and rows[0].solde == Decimal("310000.00")
    [entry] = audit(db, "correction_solde")
    assert entry.ancienne_valeur == {"date_solde": TODAY.isoformat(), "solde": "300000.00"}
    assert entry.nouvelle_valeur == {"date_solde": TODAY.isoformat(), "solde": "310000.00"}


def test_same_values_again_write_no_audit(client, tresorerie, db):
    account = add(db, "SIMTIS", "CIH")
    body = {"solde": "300000", "credit_utilise": "100000"}
    client.put(url(account), json=body, headers=tresorerie)

    client.put(url(account), json=body, headers=tresorerie)

    assert audit(db, "correction_solde") == []


def test_negative_balance_is_accepted(client, tresorerie, db):
    """Un compte à découvert a un solde négatif."""
    account = add(db, "SIMTIS", "CIH")

    response = client.put(url(account), json={"solde": "-15000.25"}, headers=tresorerie)

    assert response.json()["solde"] == "-15000.25"


def test_past_day_can_be_entered(client, tresorerie, db):
    account = add(db, "SIMTIS", "CIH")

    assert (
        client.put(
            url(account, TODAY - timedelta(days=3)), json={"solde": "1"}, headers=tresorerie
        ).status_code
        == 200
    )


def test_future_day_is_refused(client, tresorerie, db):
    account = add(db, "SIMTIS", "CIH")

    response = client.put(
        url(account, TODAY + timedelta(days=1)), json={"solde": "1"}, headers=tresorerie
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Impossible de saisir un solde pour une date future."}


def test_day_before_2000_is_refused(client, tresorerie, db):
    """Une année mal saisie (« 0026 ») ferait générer des milliers de jours au tableau Banques."""
    account = add(db, "SIMTIS", "CIH")

    response = client.put(url(account, date(1999, 12, 31)), json={"solde": "1"}, headers=tresorerie)
    accepted = client.put(url(account, date(2000, 1, 1)), json={"solde": "1"}, headers=tresorerie)

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Impossible de saisir un solde avant le 01/01/2000 : vérifiez l'année."
    }
    assert accepted.status_code == 200


def test_inactive_account_is_refused(client, tresorerie, db):
    account = add(db, "SIMTIS", "CIH", actif=False)

    response = client.put(url(account), json={"solde": "1"}, headers=tresorerie)

    assert response.status_code == 409
    assert "inactif" in response.json()["detail"]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"solde": None, "credit_utilise": None},
        {"credit_utilise": "-1"},
        {"solde": "1.234"},
        {"solde": "1", "inconnu": "x"},
    ],
)
def test_invalid_entry_gives_422(client, tresorerie, db, body):
    account = add(db, "SIMTIS", "CIH")

    assert client.put(url(account), json=body, headers=tresorerie).status_code == 422


def test_unknown_account_gives_404(client, tresorerie):
    assert (
        client.put(
            f"/api/accounts/999999/balances/{TODAY}", json={"solde": "1"}, headers=tresorerie
        ).status_code
        == 404
    )


def test_direction_cannot_enter_a_balance(client, direction, db):
    account = add(db, "SIMTIS", "CIH")

    assert client.put(url(account), json={"solde": "1"}, headers=direction).status_code == 403
    assert db.scalar(select(BankAccountBalance).filter_by(bank_account_id=account.id)) is None


# --- Historique ----------------------------------------------------------------------------------


def test_history_is_newest_first_and_filtered_by_dates(client, direction, db):
    account = add(db, "SIMTIS", "CIH")
    for days, solde in ((0, "3"), (1, "2"), (2, "1"), (40, "0")):
        save(
            db,
            BankAccountBalance(
                bank_account_id=account.id,
                date_solde=TODAY - timedelta(days=days),
                solde=Decimal(solde),
            ),
        )
    path = f"/api/accounts/{account.id}/balances"

    default = client.get(path, headers=direction).json()
    window = client.get(
        path,
        params={
            "from": (TODAY - timedelta(days=2)).isoformat(),
            "to": (TODAY - timedelta(days=1)).isoformat(),
        },
        headers=direction,
    ).json()

    assert [row["solde"] for row in default] == ["3.00", "2.00", "1.00"]  # 30 derniers jours
    assert [row["solde"] for row in window] == ["2.00", "1.00"]


def test_history_with_reversed_dates_gives_409(client, direction, db):
    account = add(db, "SIMTIS", "CIH")

    response = client.get(
        f"/api/accounts/{account.id}/balances",
        params={"from": TODAY.isoformat(), "to": (TODAY - timedelta(days=1)).isoformat()},
        headers=direction,
    )

    assert response.status_code == 409


# --- Chiffres des comptes ------------------------------------------------------------------------


def test_account_figures_follow_the_cdc_formulas(client, tresorerie, db):
    account = add(db, "SIMTIS", "CIH", credit_autorise=Decimal("500000"))
    client.put(
        url(account), json={"solde": "300000", "credit_utilise": "100000"}, headers=tresorerie
    )

    [item] = client.get(
        "/api/accounts", params={"company_id": company(db, "SIMTIS").id}, headers=tresorerie
    ).json()

    assert item["figures"] == {
        "solde": "300000.00",
        "credit_utilise": "100000.00",
        "credit_disponible": "400000.00",
        "position_disponible": "700000.00",
        "date_maj": TODAY.isoformat(),
    }


def test_figures_use_the_latest_known_value_of_each_field(client, tresorerie, db):
    account = add(db, "SIMTIS", "CIH", credit_autorise=Decimal("500000"))
    client.put(
        url(account, TODAY - timedelta(days=1)),
        json={"credit_utilise": "50000"},
        headers=tresorerie,
    )
    client.put(url(account), json={"solde": "200000"}, headers=tresorerie)

    figures = client.get(f"/api/accounts/{account.id}", headers=tresorerie).json()["figures"]

    assert figures["credit_disponible"] == "450000.00"
    assert figures["position_disponible"] == "650000.00"
    assert figures["date_maj"] == TODAY.isoformat()


def test_unknown_used_credit_is_never_treated_as_zero(client, tresorerie, db):
    account = add(db, "SIMTIS", "CIH", credit_autorise=Decimal("500000"))
    client.put(url(account), json={"solde": "200000"}, headers=tresorerie)

    figures = client.get(f"/api/accounts/{account.id}", headers=tresorerie).json()["figures"]

    assert figures["solde"] == "200000.00"
    assert figures["credit_disponible"] is None
    assert figures["position_disponible"] is None


def test_overdraft_shows_a_negative_available_credit(client, tresorerie, db):
    account = add(db, "SIMTIS", "CIH", credit_autorise=Decimal("100000"))
    client.put(
        url(account), json={"solde": "-120000", "credit_utilise": "120000"}, headers=tresorerie
    )

    figures = client.get(f"/api/accounts/{account.id}", headers=tresorerie).json()["figures"]

    assert figures["credit_disponible"] == "-20000.00"
    assert figures["position_disponible"] == "-140000.00"


def test_account_without_any_balance_has_empty_figures(client, direction, db):
    account = add(db, "SIMTIS", "CIH")

    figures = client.get(f"/api/accounts/{account.id}", headers=direction).json()["figures"]

    assert figures == {
        "solde": None,
        "credit_utilise": None,
        "credit_disponible": None,
        "position_disponible": None,
        "date_maj": None,
    }


# --- Chiffres des banques ------------------------------------------------------------------------


def bank_item(client, headers, company_id: int | None, code: str) -> dict:
    params = {} if company_id is None else {"company_id": company_id}
    return next(
        item
        for item in client.get("/api/banks", params=params, headers=headers).json()
        if item["code"] == code
    )


def test_bank_card_shows_the_mad_current_account_and_lists_the_others(client, tresorerie, db):
    mad = add(db, "SIMTIS", "CIH", credit_autorise=Decimal("800000"))
    eur = add(db, "SIMTIS", "CIH", devise="EUR")
    dhc = add(db, "SIMTIS", "CIH", type_compte="DH convertible")
    client.put(url(mad), json={"solde": "1200000", "credit_utilise": "300000"}, headers=tresorerie)
    client.put(url(eur), json={"solde": "25000"}, headers=tresorerie)
    client.put(url(dhc), json={"solde": "90000"}, headers=tresorerie)

    cih = bank_item(client, tresorerie, company(db, "SIMTIS").id, "CIH")

    assert cih["figures"]["solde"] == "1200000.00"
    assert cih["figures"]["credit_disponible"] == "500000.00"
    assert cih["figures"]["position_disponible"] == "1700000.00"
    # Les autres comptes restent dans leur devise, jamais additionnés au MAD
    assert sorted((o["devise"], o["type_compte"], o["solde"]) for o in cih["autres_comptes"]) == [
        ("EUR", "Courant", "25000.00"),
        ("MAD", "DH convertible", "90000.00"),
    ]


def test_bank_card_never_shows_the_other_company(client, tresorerie, db):
    socx = add(db, "SOCX", "CIH")
    client.put(url(socx), json={"solde": "999999", "credit_utilise": "0"}, headers=tresorerie)

    cih = bank_item(client, tresorerie, company(db, "SIMTIS").id, "CIH")

    assert cih["figures"] is None
    assert cih["autres_comptes"] == []


def test_inactive_accounts_are_not_on_the_card(client, tresorerie, db):
    mad = add(db, "SIMTIS", "CIH")
    client.put(url(mad), json={"solde": "1"}, headers=tresorerie)
    mad.actif = False
    db.flush()

    assert bank_item(client, tresorerie, company(db, "SIMTIS").id, "CIH")["figures"] is None
