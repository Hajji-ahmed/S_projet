"""Grand livre lu directement dans la base Sage (21/11/2026) : « Récupérer le GL ».

La base Sage n'est joignable que depuis le serveur de production : ici, le dépôt
`sage_sql_repository` est remplacé par un faux qui renvoie des lignes au format de la requête.
"""

from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models import (
    AccountingEntry,
    AuditLog,
    Bank,
    BankAccount,
    ColumnMapping,
    Company,
    ImportBatch,
    UserCompany,
)
from app.services import sage_sql_service
from tests.helpers import bearer, build_account, login, make_auth_user, save
from tests.sage_faux import FauxSage

ETAT = "/api/accounting/sage/etat"
ANALYSE = "/api/accounting/sage/analyse"
CONFIRM = "/api/accounting/sage/confirm"


def ligne(jour, journal, compte, piece, libelle, debit=None, credit=None, ech=None) -> tuple:
    """Une ligne telle que la renvoie la requête (ordre de `COLONNES_GL`)."""
    return (
        datetime(2025, 9, jour),
        journal,
        compte,
        piece,
        libelle,
        ech,
        None if debit is None else Decimal(debit),
        None if credit is None else Decimal(credit),
    )


@pytest.fixture
def comptable(client, reference) -> dict[str, str]:
    make_auth_user(reference, "COMPTABLE", email="comptable@example.com")
    return bearer(login(client, "comptable@example.com"))


def company(db, code: str = "SIMTIS") -> Company:
    return db.scalar(select(Company).filter_by(code=code))


def account(db, bank_code, journal, compte, company_code="SIMTIS", **over) -> BankAccount:
    bank = db.scalar(select(Bank).filter_by(code=bank_code))
    return save(
        db,
        build_account(
            company(db, company_code),
            bank,
            journal_sage=journal,
            compte_comptable=compte,
            type_compte=over.pop("type_compte", "Courant"),
            **over,
        ),
    )


@pytest.fixture
def comptes(db, reference) -> tuple[BankAccount, BankAccount]:
    """AWB et BP en courant MAD, plus un compte USD avec journal qui ne doit pas être lu."""
    awb = account(db, "AWB", "5542,5242", "55410002")
    bp = account(db, "BP", "5543,5243", "55410003")
    account(db, "AWB", "5319", "51410022", devise="USD")
    return awb, bp


def remplir(sage: FauxSage) -> None:
    sage.lignes = {
        "5542": [
            ligne(2, "5542", "55410002", "AW001", "VIR CLIENT ATLAS", debit="38500.00"),
            ligne(3, "5542", "55410002", "AW002", "CHQ 163648 HAPAG", credit="25903.00"),
        ],
        "5242": [ligne(4, "5242", "55410002", "RMS01", "EAR DA 95 SQALI", debit="21500.00")],
        "5543": [ligne(5, "5543", "55410003", "BP001", "FRAIS TENUE", credit="120.00")],
    }


def periode(db, code="SIMTIS", du="2025-09-01", au="2025-09-30") -> dict:
    return {"company_id": company(db, code).id, "du": du, "au": au}


def analyser(client, headers, db, **over):
    return client.post(ANALYSE, json=periode(db) | over, headers=headers)


def confirmer(client, headers, db, item, lignes=None, **over):
    body = periode(db) | {
        "bank_account_id": item["compte"]["bank_account_id"],
        "empreinte": item["empreinte"],
        "lignes_choisies": lignes
        if lignes is not None
        else [line["numero"] for line in item["analyse"]["lignes"] if line["statut"] == "Valide"],
    }
    return client.post(CONFIRM, json=body | over, headers=headers)


# --- État ------------------------------------------------------------------------------------------


def test_state_without_configuration_lists_the_accounts_but_refuses(client, comptable, db, comptes):
    response = client.get(ETAT, params={"company_id": company(db).id}, headers=comptable)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["configure"] is False
    assert body["message"] == (
        "La récupération depuis la base Sage n'est pas configurée sur ce serveur."
    )
    assert [c["bank_code"] for c in body["comptes"]] == ["AWB", "BP"]


def test_state_gives_the_last_copy_date(client, comptable, db, comptes, sage):
    response = client.get(ETAT, params={"company_id": company(db).id}, headers=comptable)

    body = response.json()
    assert body["configure"] is True
    assert body["base"] == "SF_TEST"
    assert body["derniere_copie"] == "2025-09-30T00:33:00"
    assert body["comptes"][0] == {
        "bank_account_id": comptes[0].id,
        "bank_code": "AWB",
        "libelle": "Compte test",
        "numero": comptes[0].numero,
        "journaux": ["5542", "5242"],
        "comptes": ["55410002"],
    }


def test_state_says_when_the_database_cannot_be_reached(client, comptable, db, comptes, sage):
    sage.panne = True

    body = client.get(ETAT, params={"company_id": company(db).id}, headers=comptable).json()

    assert body["configure"] is True
    assert body["derniere_copie"] is None
    assert body["message"] == sage_sql_service.INJOIGNABLE


def test_another_company_has_no_sage_database(client, comptable, db, reference, sage):
    response = client.get(ETAT, params={"company_id": company(db, "SOCX").id}, headers=comptable)
    assert response.json()["configure"] is False
    assert (
        response.json()["message"]
        == f"Pas de base Sage reliée à la société {company(db, 'SOCX').nom}."
    )

    response = analyser(client, comptable, db, company_id=company(db, "SOCX").id)
    assert response.status_code == 409


# --- Analyse ---------------------------------------------------------------------------------------


def test_each_mad_current_account_gets_its_own_preview(client, comptable, db, comptes, sage):
    awb, bp = comptes
    remplir(sage)

    response = analyser(client, comptable, db)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["derniere_copie"] == "2025-09-30T00:33:00"
    # Le compte USD a un journal, mais seuls les comptes courants MAD sont lus
    assert sage.lectures == [
        {"journaux": ["5542", "5242"], "comptes": ["55410002"]},
        {"journaux": ["5543", "5243"], "comptes": ["55410003"]},
    ]
    item_awb, item_bp = body["comptes"]
    assert item_awb["compte"]["bank_account_id"] == awb.id
    assert len(item_awb["empreinte"]) == 64
    analyse = item_awb["analyse"]
    assert analyse["fichier_nom"] == "GL Sage AWB 5542-5242 du 01-09-2025 au 30-09-2025.xlsx"
    assert analyse["mapping_source"] == "Utilisateur"
    assert analyse["erreurs_mapping"] == []
    assert [
        (line["date_ecriture"], line["journal"], line["numero_piece"], line["libelle"],
         line["debit"], line["credit"], line["bank_account_id"], line["statut"])
        for line in analyse["lignes"]
    ] == [
        ("2025-09-02", "5542", "AW001", "VIR CLIENT ATLAS", "38500.00", "0.00", awb.id, "Valide"),
        ("2025-09-03", "5542", "AW002", "CHQ 163648 HAPAG", "0.00", "25903.00", awb.id, "Valide"),
        ("2025-09-04", "5242", "RMS01", "EAR DA 95 SQALI", "21500.00", "0.00", awb.id, "Valide"),
    ]  # fmt: skip
    # Ni référence ni tiers : les exports Excel n'en ont jamais eu (empreinte des doublons)
    assert {line["reference"] for line in analyse["lignes"]} == {None}
    assert [line["bank_account_id"] for line in item_bp["analyse"]["lignes"]] == [bp.id]


def test_an_account_without_lines_in_the_period_gets_an_empty_preview(
    client, comptable, db, comptes, sage
):
    response = analyser(client, comptable, db)

    assert response.status_code == 200, response.text
    assert [item["analyse"]["lignes"] for item in response.json()["comptes"]] == [[], []]


def test_preview_refusals(client, comptable, db, comptes, sage):
    response = analyser(client, comptable, db, du="2025-09-30", au="2025-09-01")
    assert response.status_code == 409
    assert response.json()["detail"] == "La date de début doit précéder la date de fin."

    sage.panne = True
    response = analyser(client, comptable, db)
    assert response.status_code == 409
    assert response.json()["detail"] == sage_sql_service.INJOIGNABLE


def test_preview_is_refused_without_configuration(client, comptable, db, comptes):
    response = analyser(client, comptable, db)

    assert response.status_code == 409
    assert "pas configurée" in response.json()["detail"]


# --- Confirmation ----------------------------------------------------------------------------------


def test_confirming_one_account_imports_its_checked_lines_only(
    client, comptable, db, comptes, sage
):
    awb, bp = comptes
    remplir(sage)
    item_awb, _item_bp = analyser(client, comptable, db).json()["comptes"]
    premiere = item_awb["analyse"]["lignes"][0]["numero"]

    response = confirmer(client, comptable, db, item_awb, lignes=[premiere])

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["nb_importees"] == 1
    assert body["fichier_nom"] == "GL Sage AWB 5542-5242 du 01-09-2025 au 30-09-2025.xlsx"
    assert body["modele_enregistre"] is False
    entries = list(
        db.scalars(select(AccountingEntry).where(AccountingEntry.company_id == awb.company_id))
    )
    assert [(e.bank_account_id, e.journal, e.compte, e.numero_piece, e.debit) for e in entries] == [
        (awb.id, "5542", "55410002", "AW001", Decimal("38500.00"))
    ]
    batch = db.get(ImportBatch, body["import_id"])
    assert batch.type == "Comptabilité"
    audit = db.scalar(
        select(AuditLog).filter_by(action="import_ecritures", entite_id=str(batch.id))
    )
    assert audit.nouvelle_valeur["ecritures"] == 1
    # Les colonnes de la base Sage ne remplacent pas le modèle des exports Excel
    assert db.scalar(select(func.count()).select_from(ColumnMapping)) == 0


def test_lines_already_imported_come_back_as_duplicates(client, comptable, db, comptes, sage):
    remplir(sage)
    item_awb = analyser(client, comptable, db).json()["comptes"][0]
    assert confirmer(client, comptable, db, item_awb).status_code == 201

    again = analyser(client, comptable, db).json()["comptes"][0]["analyse"]

    assert {line["statut"] for line in again["lignes"]} == {"Doublon"}
    assert again["resume"]["nb_doublons"] == 3


def test_confirmation_is_refused_when_sage_changed_since_the_preview(
    client, comptable, db, comptes, sage
):
    remplir(sage)
    item_awb = analyser(client, comptable, db).json()["comptes"][0]
    sage.lignes["5542"].append(ligne(6, "5542", "55410002", "AW003", "VIR NOUVEAU", debit="10.00"))

    response = confirmer(client, comptable, db, item_awb)

    assert response.status_code == 409
    assert response.json()["detail"] == sage_sql_service.BASE_CHANGEE
    assert db.scalar(select(func.count()).select_from(AccountingEntry)) == 0


def test_only_the_accounts_read_from_sage_can_be_confirmed(client, comptable, db, comptes, sage):
    remplir(sage)
    item_awb = analyser(client, comptable, db).json()["comptes"][0]
    usd = db.scalar(select(BankAccount).filter_by(devise="USD"))

    response = confirmer(client, comptable, db, item_awb, bank_account_id=usd.id)

    assert response.status_code == 404


def test_confirmation_needs_at_least_one_line(client, comptable, db, comptes, sage):
    remplir(sage)
    item_awb = analyser(client, comptable, db).json()["comptes"][0]

    response = confirmer(client, comptable, db, item_awb, lignes=[])

    assert response.status_code == 409


# --- Droits ----------------------------------------------------------------------------------------


def test_reading_only_roles_cannot_use_sage(client, reference, db, comptes, sage):
    make_auth_user(reference, "DIRECTION", email="direction@example.com")
    headers = bearer(login(client, "direction@example.com"))

    assert (
        client.get(ETAT, params={"company_id": company(db).id}, headers=headers).status_code == 403
    )
    assert analyser(client, headers, db).status_code == 403


def test_a_person_limited_to_another_company_is_refused(client, reference, db, comptes, sage):
    user = make_auth_user(reference, "COMPTABLE", email="limite@example.com")
    save(reference, UserCompany(user_id=user.id, company_id=company(db, "SOCX").id))
    headers = bearer(login(client, "limite@example.com"))
    remplir(sage)

    assert (
        client.get(ETAT, params={"company_id": company(db).id}, headers=headers).status_code == 403
    )
    assert analyser(client, headers, db).status_code == 403
    body = periode(db) | {
        "bank_account_id": comptes[0].id,
        "empreinte": "0" * 64,
        "lignes_choisies": [2],
    }
    assert client.post(CONFIRM, json=body, headers=headers).status_code == 403
