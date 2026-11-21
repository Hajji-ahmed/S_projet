"""Écart entre le solde d'un compte dans Sage et son solde comptable SIMTIS (21/11/2026).

Même faux dépôt Sage que `test_sage_sql.py` (la vraie base n'est joignable que depuis le serveur
de production).
"""

from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Company, UserCompany
from tests.helpers import bearer, build_entry, login, make_auth_user, save
from tests.sage_faux import FauxSage
from tests.test_sage_sql import account

SOLDES = "/api/accounting/sage/soldes"
ECART = "/api/accounting/sage/ecart"
COMPARAISON = "/api/accounting/sage/comparaison"
ANALYSE = "/api/accounting/sage/analyse"
CONFIRM = "/api/accounting/sage/confirm"
JOUR = "2025-09-30"


def ligne(quand: date, journal, compte, piece, libelle, debit=None, credit=None) -> tuple:
    return (
        datetime(quand.year, quand.month, quand.day),
        journal,
        compte,
        piece,
        libelle,
        None,
        None if debit is None else Decimal(debit),
        None if credit is None else Decimal(credit),
    )


@pytest.fixture
def comptable(client, reference) -> dict[str, str]:
    make_auth_user(reference, "COMPTABLE", email="comptable@example.com")
    return bearer(login(client, "comptable@example.com"))


def company(db, code="SIMTIS") -> Company:
    return db.scalar(select(Company).filter_by(code=code))


@pytest.fixture
def awb(db, reference):
    """Compte AWB : ouverture SIMTIS de 1 000 au 31/12/2024."""
    return account(
        db,
        "AWB",
        "5542,5242",
        "55410002",
        date_solde_comptable=date(2024, 12, 31),
        solde_comptable_ouverture=Decimal("1000.00"),
    )


def remplir(sage: FauxSage) -> None:
    sage.lignes = {
        # L'à-nouveau 2024 précède le dernier à-nouveau : il ne compte pas
        "9000": [
            ligne(date(2024, 1, 1), "9000", "55410002", "AN24", "A NOUVEAU", debit="500.00"),
            ligne(date(2025, 1, 1), "9000", "55410002", "AN25", "A NOUVEAU", debit="1000.00"),
        ],
        "5542": [ligne(date(2025, 9, 2), "5542", "55410002", "AW1", "VIR ATLAS", debit="300.00")],
        "5242": [ligne(date(2025, 9, 3), "5242", "55410002", "RM1", "EAR SQALI", credit="100.00")],
        # OD passée dans Sage, jamais importée par SIMTIS
        "1000": [ligne(date(2025, 9, 4), "1000", "55410002", "OD1", "REGUL", credit="50.00")],
    }


def importer(client, headers, db) -> None:
    """Importe le grand livre de septembre par « Récupérer le GL »."""
    body = {"company_id": company(db).id, "du": "2025-09-01", "au": JOUR}
    item = client.post(ANALYSE, json=body, headers=headers).json()["comptes"][0]
    lignes = [line["numero"] for line in item["analyse"]["lignes"] if line["statut"] == "Valide"]
    response = client.post(
        CONFIRM,
        json=body
        | {
            "bank_account_id": item["compte"]["bank_account_id"],
            "empreinte": item["empreinte"],
            "lignes_choisies": lignes,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text


@pytest.fixture
def monde(client, comptable, db, awb, sage):
    """Sage : à-nouveau 1 000, +300, −100, OD −50 → 1 150. SIMTIS : ouverture 1 000, les deux
    lignes de banque importées, un frais SIMTIS de 20 pas encore exporté → 1 180. Écart −30."""
    remplir(sage)
    importer(client, comptable, db)
    save(
        db,
        build_entry(
            company(db),
            bank_account_id=awb.id,
            journal="5542",
            compte="55410002",
            date_ecriture=date(2025, 9, 10),
            libelle="FRAIS TENUE",
            debit=Decimal("0"),
            credit=Decimal("20.00"),
            montant=Decimal("20.00"),
            origine="SIMTIS",
            famille_frais="frais",
        ),
    )
    return awb


def test_each_account_gets_its_sage_balance_and_the_gap(client, comptable, db, monde):
    response = client.get(
        SOLDES, params={"company_id": company(db).id, "date": JOUR}, headers=comptable
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["configure"] is True
    assert body["derniere_copie"] == "2025-09-30T00:33:00"
    [item] = body["comptes"]
    assert item["bank_account_id"] == monde.id
    assert item["debut"] == "2025-01-01"
    assert item["solde_sage"] == "1150.00"
    assert item["solde_simtis"] == "1180.00"
    assert item["ecart"] == "-30.00"


def test_the_detail_explains_the_gap_journal_by_journal(client, comptable, monde):
    response = client.get(
        ECART, params={"bank_account_id": monde.id, "date": JOUR}, headers=comptable
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["depart_sage"] == "1000.00"
    assert body["depart_simtis"] == "1000.00"
    assert body["debut_simtis"] == "2025-01-01"
    assert [
        (j["journal"], j["banque"], j["sage"], j["simtis"], j["ecart"], j["nb_sage"], j["nb_simtis"])
        for j in body["journaux"]
    ] == [
        ("5542", True, "300.00", "300.00", "0.00", 1, 1),
        ("5242", True, "-100.00", "-100.00", "0.00", 1, 1),
        ("1000", False, "-50.00", "0.00", "-50.00", 1, 0),
    ]  # fmt: skip
    assert body["non_exportees"] == "-20.00"
    assert body["nb_non_exportees"] == 1
    assert [(line["journal"], line["numero_piece"], line["credit"]) for line in body["hors_journaux"]] == [
        ("1000", "OD1", "50.00")
    ]  # fmt: skip
    assert body["hors_journaux_tronque"] is False
    # départ + journaux − non exportées = écart total
    ecart = (
        Decimal(body["depart_sage"])
        - Decimal(body["depart_simtis"])
        + sum(Decimal(j["ecart"]) for j in body["journaux"])
        - Decimal(body["non_exportees"])
    )
    assert ecart == Decimal(body["solde"]["ecart"])


def test_line_by_line_comparison_shows_what_is_on_one_side_only(client, comptable, monde, sage):
    # Une ligne saisie dans Sage après l'import, une autre supprimée de Sage
    sage.lignes["5542"].append(
        ligne(date(2025, 9, 20), "5542", "55410002", "AW2", "VIR NOUVEAU", debit="75.00")
    )
    sage.lignes["5242"] = []

    response = client.get(
        COMPARAISON, params={"bank_account_id": monde.id, "date": JOUR}, headers=comptable
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [(line["numero_piece"], line["debit"]) for line in body["absentes_de_simtis"]] == [
        ("AW2", "75.00")
    ]
    assert [(item["numero_piece"], item["credit"]) for item in body["absentes_de_sage"]] == [
        ("RM1", "100.00")
    ]


def test_without_simtis_opening_only_the_sage_balance_is_given(client, comptable, db, sage):
    account(db, "BP", "5543", "55410003")
    sage.lignes = {"5543": [ligne(date(2025, 9, 2), "5543", "55410003", "B1", "X", debit="10.00")]}

    body = client.get(
        SOLDES, params={"company_id": company(db).id, "date": JOUR}, headers=comptable
    ).json()

    [item] = body["comptes"]
    assert item["debut"] == "2025-09-02"  # pas d'à-nouveau : première écriture
    assert item["solde_sage"] == "10.00"
    assert item["solde_simtis"] is None
    assert item["ecart"] is None


def test_the_gl_preview_gives_the_sage_balance_at_the_end_date(client, comptable, db, awb, sage):
    remplir(sage)
    body = {"company_id": company(db).id, "du": "2025-09-01", "au": JOUR}

    item = client.post(ANALYSE, json=body, headers=comptable).json()["comptes"][0]

    assert item["solde_sage"] == "1150.00"
    assert item["debut_sage"] == "2025-01-01"


def test_unreachable_or_unconfigured_sage_does_not_break_the_balances(
    client, comptable, db, awb, sage, monkeypatch
):
    sage.panne = True
    body = client.get(SOLDES, params={"company_id": company(db).id}, headers=comptable).json()
    assert body["configure"] is True
    assert body["comptes"] == []
    assert "injoignable" in body["message"]

    body = client.get(SOLDES, params={"company_id": company(db, "SOCX").id}, headers=comptable)
    assert body.json()["configure"] is False


def test_only_mad_current_accounts_are_compared(client, comptable, db, awb, sage):
    usd = account(db, "AWB", "5319", "51410022", devise="USD")

    response = client.get(ECART, params={"bank_account_id": usd.id}, headers=comptable)

    assert response.status_code == 409


def test_reading_roles_see_the_gap_and_other_companies_are_refused(
    client, reference, db, awb, sage
):
    make_auth_user(reference, "DIRECTION", email="direction@example.com")
    direction = bearer(login(client, "direction@example.com"))
    # Lecture comme la carte « Solde comptable » : la Direction consulte le rapprochement
    assert (
        client.get(SOLDES, params={"company_id": company(db).id}, headers=direction).status_code
        == 200
    )

    user = make_auth_user(reference, "COMPTABLE", email="limite@example.com")
    save(reference, UserCompany(user_id=user.id, company_id=company(db, "SOCX").id))
    limite = bearer(login(client, "limite@example.com"))
    for url, params in (
        (SOLDES, {"company_id": company(db).id}),
        (ECART, {"bank_account_id": awb.id}),
        (COMPARAISON, {"bank_account_id": awb.id}),
    ):
        assert client.get(url, params=params, headers=limite).status_code == 403
