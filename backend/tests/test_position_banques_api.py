"""Tableau Banques calculé (P8.1) : GET /api/position/banques."""

from datetime import date, timedelta
from decimal import Decimal
from itertools import count

import pytest
from sqlalchemy import select

from app.models import Bank, BankAccount, BankAccountBalance, BankStatement, Company
from app.services.position_service import business_today
from tests.helpers import bearer, build_account, build_transaction, login, make_auth_user, save

URL = "/api/position/banques"
# Dates passées : aucun résultat ne dépend du décalage horaire du Maroc
J28, J29, J30 = date(2025, 9, 28), date(2025, 9, 29), date(2025, 9, 30)
_numeros = count(1)


@pytest.fixture
def direction(client, reference) -> dict[str, str]:
    make_auth_user(reference, "DIRECTION", email="direction@example.com")
    return bearer(login(client, "direction@example.com"))


def company(db, code: str = "SIMTIS") -> Company:
    return db.scalar(select(Company).filter_by(code=code))


def bank(db, code: str) -> Bank:
    return db.scalar(select(Bank).filter_by(code=code))


def account(db, bank_code: str, company_code: str = "SIMTIS", **over) -> BankAccount:
    over.setdefault("numero", f"RIB-POS-{next(_numeros):06d}")
    over.setdefault("type_compte", "Courant")
    return save(db, build_account(company(db, company_code), bank(db, bank_code), **over))


def balance(db, compte: BankAccount, jour: date, solde=None, credit_utilise=None) -> None:
    save(
        db,
        BankAccountBalance(
            bank_account_id=compte.id,
            date_solde=jour,
            solde=None if solde is None else Decimal(solde),
            credit_utilise=None if credit_utilise is None else Decimal(credit_utilise),
        ),
    )


def get(client, headers, db, jour: date | None = J30, code: str = "SIMTIS"):
    params = {"company_id": str(company(db, code).id)}
    if jour is not None:
        params["date"] = jour.isoformat()
    return client.get(URL, params=params, headers=headers)


def cell(body: dict, line: dict, code: str) -> dict:
    index = [banque["code"] for banque in body["banques"]].index(code)
    return line["cellules"][index]


def test_validated_example_through_the_api(client, direction, db):
    # Valeurs telles que la base les rend (NUMERIC(18,2), NUMERIC(18,6)) : l'objet n'est pas relu
    awb = account(db, "AWB", credit_autorise=Decimal("500000.00"), taux_interet=Decimal("0.055000"))
    bmce = account(db, "BMCE", credit_autorise=Decimal("300000.00"))
    balance(db, awb, J30, "-200000")
    balance(db, bmce, J30, "100000")

    response = get(client, direction, db)

    assert response.status_code == 200
    body = response.json()
    assert body["company_id"] == company(db).id
    assert body["date_fin"] == "2025-09-30"
    assert [banque["code"] for banque in body["banques"]] == ["AWB", "BMCE", "BP", "CIH", "BMCI"]
    assert body["banques"][0] == {
        "bank_id": bank(db, "AWB").id,
        "code": "AWB",
        "logo": "/banques/attijariwafa.png",
        "bank_account_id": awb.id,
        "taux_pct": "5.5",
        "ligne": "500000.00",
    }
    assert body["banques"][1]["taux_pct"] is None
    assert body["banques"][2] | {"bank_id": 0} == {
        "bank_id": 0,
        "code": "BP",
        "logo": "/banques/bp.png",
        "bank_account_id": None,
        "taux_pct": None,
        "ligne": None,
    }
    assert body["ligne_total"] == "800000.00"
    [jour] = body["jours"]
    assert jour["date"] == "2025-09-30"
    assert cell(body, jour, "AWB") == {
        "bank_id": bank(db, "AWB").id,
        "valeur": "300000.00",
        "date_solde": "2025-09-30",
        "reprise": False,
    }
    assert cell(body, jour, "BMCE")["valeur"] == "400000.00"
    assert cell(body, jour, "BP")["valeur"] is None
    assert jour["total"] == "700000.00"
    assert jour["depassement"] == "-100000.00"
    # Disponible Fc reel = facilité du dernier jour − LIGNE (décision du 03/10/2026)
    assert cell(body, body["disponible"], "AWB")["valeur"] == "-200000.00"
    assert cell(body, body["disponible"], "BMCE")["valeur"] == "100000.00"
    assert body["disponible"]["total"] == "-100000.00"
    assert body["disponible"]["depassement"] == "-100000.00"  # = TOTAL (LIGNE déjà retirée)


def test_only_the_active_mad_current_account_counts(client, direction, db):
    courant = account(db, "AWB")
    balance(db, courant, J30, "1000")
    for other in (
        account(db, "AWB", type_compte="DH convertible"),
        account(db, "AWB", devise="EUR"),
        account(db, "AWB", actif=False),  # ancien compte courant MAD désactivé
    ):
        balance(db, other, J30, "999999")

    body = get(client, direction, db).json()

    assert body["banques"][0]["bank_account_id"] == courant.id
    assert cell(body, body["jours"][0], "AWB")["valeur"] == "1000.00"
    assert body["jours"][0]["total"] == "1000.00"


def test_other_company_is_excluded(client, direction, db):
    balance(db, account(db, "AWB", company_code="SOCX"), J30, "5000")

    body = get(client, direction, db).json()

    assert body["banques"][0]["bank_account_id"] is None
    assert body["jours"] == []


def test_inactive_bank_has_no_column(client, direction, db):
    bank(db, "BMCE").actif = False
    db.flush()

    body = get(client, direction, db).json()

    assert [banque["code"] for banque in body["banques"]] == ["AWB", "BP", "CIH", "BMCI"]


def test_balance_row_without_solde_does_not_count(client, direction, db):
    awb = account(db, "AWB")
    balance(db, awb, J28, "1000")
    balance(db, awb, J29, credit_utilise="50")  # crédit utilisé seul

    body = get(client, direction, db, J29).json()

    assert cell(body, body["jours"][-1], "AWB") | {"bank_id": 0} == {
        "bank_id": 0,
        "valeur": "1000.00",
        "date_solde": "2025-09-28",
        "reprise": True,
    }


def test_balance_before_2000_is_ignored(client, direction, db):
    """Une année mal saisie (« 0026 », « 1999 ») ne doit pas créer des milliers de lignes."""
    awb = account(db, "AWB")
    balance(db, awb, date(1999, 12, 31), "5")
    balance(db, awb, J30, "1")

    body = get(client, direction, db).json()

    assert [jour["date"] for jour in body["jours"]] == ["2025-09-30"]


def operations(db, compte: BankAccount, *rows: tuple[date, str | None]) -> None:
    """Opérations importées, dans l'ordre du relevé : (date d'opération, solde ou None)."""
    statement = save(db, BankStatement(bank_account_id=compte.id))
    for jour, solde in rows:
        save(
            db,
            build_transaction(
                statement,
                date_operation=jour,
                solde=None if solde is None else Decimal(solde),
            ),
        )


def test_last_operation_of_the_day_gives_the_balance(client, direction, db):
    """Décision du 03/10/2026 : solde de la dernière opération du jour (ordre du relevé), même si
    un solde du jour a été saisi ; une opération sans solde est ignorée."""
    awb = account(db, "AWB", credit_autorise=Decimal("100.00"))
    operations(db, awb, (J29, "5"), (J30, "10"), (J30, "20"), (J30, None))
    balance(db, awb, J30, "999")

    body = get(client, direction, db).json()

    j29, j30 = body["jours"]
    assert cell(body, j29, "AWB")["valeur"] == "105.00"
    assert cell(body, j30, "AWB") | {"bank_id": 0} == {
        "bank_id": 0,
        "valeur": "120.00",
        "date_solde": "2025-09-30",
        "reprise": False,
    }
    assert cell(body, body["disponible"], "AWB")["valeur"] == "20.00"


def test_an_account_with_a_statement_ignores_entered_balances(client, direction, db):
    """Décision du 08/10/2026 : un compte alimenté par un relevé ne lit que son relevé, pour que
    « Disponible Fc reel » soit son solde de clôture ; une saisie plus récente est ignorée."""
    awb = account(db, "AWB")
    operations(db, awb, (J28, "5"))
    balance(db, awb, J29, "7")
    cih = account(db, "CIH")
    balance(db, cih, J29, "7")  # sans relevé : la saisie compte
    other = account(db, "BP", company_code="SOCX")
    operations(db, other, (J30, "123456"))  # autre société : jamais comptée

    body = get(client, direction, db).json()

    assert [cell(body, jour, "AWB")["valeur"] for jour in body["jours"]] == [
        "5.00",
        "5.00",
        "5.00",
    ]
    assert cell(body, body["jours"][-1], "AWB")["reprise"] is True
    assert cell(body, body["jours"][-1], "CIH")["valeur"] == "7.00"
    assert cell(body, body["jours"][-1], "BP")["valeur"] is None


def test_end_date_is_capped_at_today(client, direction, db):
    balance(db, account(db, "AWB"), J30, "1")
    today = business_today()

    body = get(client, direction, db, today + timedelta(days=30)).json()

    assert body["date_fin"] == today.isoformat()
    assert body["jours"][-1]["date"] == today.isoformat()
    assert len(body["jours"]) == (today - J30).days + 1


def test_default_date_is_today(client, direction, db):
    body = get(client, direction, db, None).json()

    assert body["date_fin"] == business_today().isoformat()


def test_date_before_the_first_balance_gives_no_day(client, direction, db):
    balance(db, account(db, "AWB", credit_autorise=Decimal("100.00")), J30, "1")

    body = get(client, direction, db, J28).json()

    assert body["jours"] == []
    assert body["disponible"]["total"] is None
    assert body["disponible"]["depassement"] is None
    assert cell(body, body["disponible"], "AWB")["valeur"] is None
    assert body["ligne_total"] == "100.00"


def test_unknown_or_inactive_company_gives_404(client, direction, db):
    unknown = client.get(URL, params={"company_id": "999999"}, headers=direction)
    company(db, "SOCX").actif = False
    db.flush()
    inactive = get(client, direction, db, code="SOCX")

    for response in (unknown, inactive):
        assert response.status_code == 404
        assert response.json() == {"detail": "Société introuvable."}


def test_invalid_date_gives_422(client, direction, db):
    response = client.get(
        URL, params={"company_id": str(company(db).id), "date": "2025-02-30"}, headers=direction
    )

    assert response.status_code == 422


def test_requires_a_token(client, reference):
    assert client.get(URL, params={"company_id": "1"}).status_code == 401


def test_requires_position_view(client, reference, db):
    make_auth_user(reference, email="sans-role@example.com")
    headers = bearer(login(client, "sans-role@example.com"))

    assert get(client, headers, db).status_code == 403
