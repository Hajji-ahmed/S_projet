"""Comptes bancaires : une société à la fois, règles de création et de modification, audit."""

from datetime import date
from decimal import Decimal
from itertools import count

import pytest
from sqlalchemy import select

from app.models import (
    AuditLog,
    Bank,
    BankAccount,
    BankAccountBalance,
    BankStatement,
    Company,
)
from tests.helpers import bearer, build_account, login, make_auth_user, save

ACCOUNTS = "/api/accounts"


@pytest.fixture
def tresorerie(client, reference) -> dict[str, str]:
    make_auth_user(reference, "TRESORERIE", email="tresorerie@example.com")
    return bearer(login(client, "tresorerie@example.com"))


@pytest.fixture
def direction(client, reference) -> dict[str, str]:
    make_auth_user(reference, "DIRECTION", email="direction@example.com")
    return bearer(login(client, "direction@example.com"))


def company(db, code: str) -> Company:
    return db.scalar(select(Company).filter_by(code=code))


def bank(db, code: str) -> Bank:
    return db.scalar(select(Bank).filter_by(code=code))


def payload(db, **over) -> dict:
    return {
        "company_id": company(db, "SIMTIS").id,
        "bank_id": bank(db, "CIH").id,
        "libelle": "Compte courant",
        "numero": "230 780 0001234567890123 45",
        "devise": "MAD",
        "type_compte": "Courant",
        "compte_comptable": "5141",
        "credit_autorise": "500000.00",
        "taux_interet_pct": "4.5",
        **over,
    }


_numeros = count(1)


def add(db, company_code: str, bank_code: str, **over) -> BankAccount:
    """Compte en base, avec un numéro au format accepté par l'API (pour pouvoir le modifier)."""
    over.setdefault("numero", f"RIB-TEST-{next(_numeros):06d}")
    return save(db, build_account(company(db, company_code), bank(db, bank_code), **over))


def audit(db, action: str) -> list[AuditLog]:
    return list(db.scalars(select(AuditLog).filter_by(action=action).order_by(AuditLog.id)))


# --- Lecture : une société à la fois -------------------------------------------------------------


def test_list_requires_a_company(client, direction):
    assert client.get(ACCOUNTS, headers=direction).status_code == 422


def test_list_never_mixes_two_companies(client, direction, db):
    add(db, "SIMTIS", "CIH")
    add(db, "SOCX", "CIH")

    simtis = client.get(
        ACCOUNTS, params={"company_id": company(db, "SIMTIS").id}, headers=direction
    )

    assert simtis.status_code == 200
    assert {item["company_id"] for item in simtis.json()} == {company(db, "SIMTIS").id}
    assert len(simtis.json()) == 1


def test_list_follows_bank_order_then_mad_first(client, direction, db):
    add(db, "SIMTIS", "CIH", devise="EUR")
    add(db, "SIMTIS", "CIH", devise="MAD")
    add(db, "SIMTIS", "AWB", devise="MAD")

    items = client.get(
        ACCOUNTS, params={"company_id": company(db, "SIMTIS").id}, headers=direction
    ).json()

    assert [(item["bank_code"], item["devise"]) for item in items] == [
        ("AWB", "MAD"),
        ("CIH", "MAD"),
        ("CIH", "EUR"),
    ]


def test_list_filters(client, direction, db):
    add(db, "SIMTIS", "CIH", devise="MAD")
    add(db, "SIMTIS", "CIH", devise="EUR", actif=False)
    add(db, "SIMTIS", "AWB", devise="USD")
    simtis = company(db, "SIMTIS").id

    def codes(**params):
        response = client.get(ACCOUNTS, params={"company_id": simtis, **params}, headers=direction)
        return sorted((item["bank_code"], item["devise"]) for item in response.json())

    assert codes(bank_id=bank(db, "CIH").id) == [("CIH", "EUR"), ("CIH", "MAD")]
    assert codes(devise="usd") == [("AWB", "USD")]
    assert codes(actif=False) == [("CIH", "EUR")]


def test_amounts_are_exact_text_and_rate_is_a_percentage(client, direction, db):
    add(db, "SIMTIS", "CIH", credit_autorise=Decimal("1234567.89"), taux_interet=Decimal("0.045"))

    [item] = client.get(
        ACCOUNTS, params={"company_id": company(db, "SIMTIS").id}, headers=direction
    ).json()

    assert item["credit_autorise"] == "1234567.89"
    assert item["taux_interet_pct"] == "4.5"
    assert item["bank_logo"] == "/banques/cih.png"


def test_unknown_account_gives_404(client, direction):
    assert client.get(f"{ACCOUNTS}/999999", headers=direction).status_code == 404


# --- Création ------------------------------------------------------------------------------------


def test_create_account(client, tresorerie, db):
    response = client.post(ACCOUNTS, json=payload(db), headers=tresorerie)

    assert response.status_code == 201
    body = response.json()
    assert body["numero"] == "230780000123456789012345"  # sans espaces
    assert body["credit_autorise"] == "500000.00"
    assert body["taux_interet_pct"] == "4.5"
    account = db.get(BankAccount, body["id"])
    assert account.taux_interet == Decimal("0.045")  # stocké en fraction, sans perte


def test_create_is_audited_with_exact_amounts(client, tresorerie, db):
    client.post(ACCOUNTS, json=payload(db), headers=tresorerie)

    [entry] = audit(db, "creation_compte")
    assert entry.entite == "bank_account"
    assert entry.nouvelle_valeur["credit_autorise"] == "500000.00"
    assert entry.nouvelle_valeur["taux_interet"] == "0.045000"  # précision de la colonne
    assert entry.nouvelle_valeur["devise"] == "MAD"


def test_second_active_account_in_the_same_slot_gives_409(client, tresorerie, db):
    add(db, "SIMTIS", "CIH", devise="MAD", type_compte="Courant")

    response = client.post(ACCOUNTS, json=payload(db), headers=tresorerie)

    assert response.status_code == 409
    assert response.json() == {
        "detail": "CIH a déjà un compte courant en MAD actif pour Simtis. "
        "Désactivez-le d'abord pour en ouvrir un autre."
    }


def test_other_currency_in_the_same_bank_is_accepted(client, tresorerie, db):
    add(db, "SIMTIS", "CIH", devise="MAD")

    response = client.post(
        ACCOUNTS,
        json=payload(db, devise="EUR", credit_autorise="0", taux_interet_pct=None),
        headers=tresorerie,
    )

    assert response.status_code == 201


def test_new_account_allowed_once_the_old_one_is_deactivated(client, tresorerie, db):
    add(db, "SIMTIS", "CIH", devise="MAD", actif=False)

    assert client.post(ACCOUNTS, json=payload(db), headers=tresorerie).status_code == 201


def test_same_slot_for_the_other_company_is_accepted(client, tresorerie, db):
    add(db, "SOCX", "CIH", devise="MAD")

    assert client.post(ACCOUNTS, json=payload(db), headers=tresorerie).status_code == 201


def test_duplicate_numero_gives_409_even_with_other_spacing(client, tresorerie, db):
    add(db, "SOCX", "BP", numero="230780000123456789012345")

    response = client.post(ACCOUNTS, json=payload(db), headers=tresorerie)

    assert response.status_code == 409
    assert "déjà utilisé" in response.json()["detail"]


def test_inactive_bank_gives_409(client, tresorerie, db):
    bank(db, "CIH").actif = False
    db.flush()

    response = client.post(ACCOUNTS, json=payload(db), headers=tresorerie)

    assert response.status_code == 409
    assert response.json() == {"detail": "La banque CIH est inactive : réactivez-la d'abord."}


def test_unknown_company_or_bank_gives_404(client, tresorerie, db):
    assert (
        client.post(ACCOUNTS, json=payload(db, company_id=999999), headers=tresorerie).status_code
        == 404
    )
    assert (
        client.post(ACCOUNTS, json=payload(db, bank_id=999999), headers=tresorerie).status_code
        == 404
    )


def test_unknown_currency_gives_409(client, tresorerie, db):
    response = client.post(ACCOUNTS, json=payload(db, devise="GBP"), headers=tresorerie)

    assert response.status_code == 409
    assert response.json() == {"detail": "Devise inconnue : GBP."}


@pytest.mark.parametrize(
    "over",
    [
        {"type_compte": "DH convertible", "devise": "EUR"},
        {"type_compte": "Épargne"},
        {"credit_autorise": "-1"},
        {"credit_autorise": "100.123"},
        {"taux_interet_pct": "100.01"},
        {"taux_interet_pct": "-1"},
        {"libelle": " "},
        {"numero": "AB"},
        {"numero": "RIB/123456"},
        {"compte_comptable": "51-41"},
        {"devise": "EURO"},
        {"couleur": "bleu"},
    ],
)
def test_invalid_creation_gives_422(client, tresorerie, db, over):
    assert client.post(ACCOUNTS, json=payload(db, **over), headers=tresorerie).status_code == 422
    assert db.scalar(select(BankAccount).filter_by(numero="230780000123456789012345")) is None


def test_dh_convertible_account_in_mad(client, tresorerie, db):
    add(db, "SIMTIS", "CIH", devise="MAD")  # le compte courant n'empêche pas le DH convertible

    response = client.post(
        ACCOUNTS, json=payload(db, type_compte="DH convertible"), headers=tresorerie
    )

    assert response.status_code == 201


# --- Modification --------------------------------------------------------------------------------


def update_body(account: BankAccount, **over) -> dict:
    return {
        "libelle": account.libelle,
        "numero": account.numero,
        "type_compte": account.type_compte,
        "compte_comptable": account.compte_comptable,
        "journal_sage": account.journal_sage,
        "credit_autorise": str(account.credit_autorise),
        "taux_interet_pct": None,
        **over,
    }


def test_update_audits_only_the_changed_fields(client, tresorerie, db):
    account = add(db, "SIMTIS", "CIH", credit_autorise=Decimal("500000"))

    response = client.put(
        f"{ACCOUNTS}/{account.id}",
        json=update_body(account, credit_autorise="650000.50"),
        headers=tresorerie,
    )

    assert response.status_code == 200
    assert response.json()["credit_autorise"] == "650000.50"
    [entry] = audit(db, "modification_compte")
    assert entry.ancienne_valeur == {"credit_autorise": "500000.00"}
    assert entry.nouvelle_valeur == {"credit_autorise": "650000.50"}


def test_update_without_change_writes_no_audit(client, tresorerie, db):
    account = add(db, "SIMTIS", "CIH", credit_autorise=Decimal("500000"))

    client.put(
        f"{ACCOUNTS}/{account.id}",
        json=update_body(account, credit_autorise="500000"),
        headers=tresorerie,
    )

    assert audit(db, "modification_compte") == []


@pytest.mark.parametrize("field", ["company_id", "bank_id", "devise"])
def test_company_bank_and_currency_cannot_change(client, tresorerie, db, field):
    account = add(db, "SIMTIS", "CIH")
    other = {"company_id": company(db, "SOCX").id, "bank_id": bank(db, "AWB").id, "devise": "EUR"}

    response = client.put(
        f"{ACCOUNTS}/{account.id}",
        json=update_body(account, **{field: other[field]}),
        headers=tresorerie,
    )

    assert response.status_code == 422


def test_changing_type_into_an_occupied_slot_gives_409(client, tresorerie, db):
    add(db, "SIMTIS", "CIH", devise="MAD", type_compte="DH convertible")
    courant = add(db, "SIMTIS", "CIH", devise="MAD", type_compte="Courant")

    response = client.put(
        f"{ACCOUNTS}/{courant.id}",
        json=update_body(courant, type_compte="DH convertible"),
        headers=tresorerie,
    )

    assert response.status_code == 409


def test_eur_account_cannot_become_dh_convertible(client, tresorerie, db):
    account = add(db, "SIMTIS", "CIH", devise="EUR")

    response = client.put(
        f"{ACCOUNTS}/{account.id}",
        json=update_body(account, type_compte="DH convertible"),
        headers=tresorerie,
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Un compte DH convertible doit être en MAD."}


# --- Activation / désactivation ------------------------------------------------------------------


def test_deactivate_and_reactivate(client, tresorerie, db):
    account = add(db, "SIMTIS", "CIH")

    off = client.patch(f"{ACCOUNTS}/{account.id}/status", json={"actif": False}, headers=tresorerie)
    on = client.patch(f"{ACCOUNTS}/{account.id}/status", json={"actif": True}, headers=tresorerie)

    assert (off.json()["actif"], on.json()["actif"]) == (False, True)
    assert len(audit(db, "desactivation_compte")) == 1
    assert len(audit(db, "reactivation_compte")) == 1


def test_reactivation_refused_when_a_new_account_took_the_slot(client, tresorerie, db):
    old = add(db, "SIMTIS", "CIH", actif=False)
    add(db, "SIMTIS", "CIH")

    response = client.patch(f"{ACCOUNTS}/{old.id}/status", json={"actif": True}, headers=tresorerie)

    assert response.status_code == 409


def test_reactivation_refused_when_the_bank_is_inactive(client, tresorerie, db):
    account = add(db, "SIMTIS", "CIH", actif=False)
    bank(db, "CIH").actif = False
    db.flush()

    response = client.patch(
        f"{ACCOUNTS}/{account.id}/status", json={"actif": True}, headers=tresorerie
    )

    assert response.status_code == 409
    assert "CIH est inactive" in response.json()["detail"]


# --- Permissions et nombre de comptes par société -------------------------------------------------


def test_direction_reads_but_cannot_write(client, direction, db):
    account = add(db, "SIMTIS", "CIH")
    writes = [
        client.post(ACCOUNTS, json=payload(db, bank_id=bank(db, "AWB").id), headers=direction),
        client.put(
            f"{ACCOUNTS}/{account.id}",
            json=update_body(account, libelle="Pirate"),
            headers=direction,
        ),
        client.patch(f"{ACCOUNTS}/{account.id}/status", json={"actif": False}, headers=direction),
    ]

    assert [response.status_code for response in writes] == [403, 403, 403]
    db.refresh(account)
    assert (account.libelle, account.actif) == ("Compte test", True)


def test_bank_cards_count_accounts_of_the_active_company_only(client, direction, db):
    add(db, "SIMTIS", "CIH")
    add(db, "SIMTIS", "CIH", devise="EUR")
    add(db, "SOCX", "CIH")

    def cih_count(**params):
        banks = client.get("/api/banks", params=params, headers=direction).json()
        return next(item["nb_comptes_actifs"] for item in banks if item["code"] == "CIH")

    assert cih_count(company_id=company(db, "SIMTIS").id) == 2
    assert cih_count(company_id=company(db, "SOCX").id) == 1
    assert cih_count() == 3


# --- Journal Sage (P10) ---------------------------------------------------------------------------


def test_journal_sage_is_saved_in_capitals(client, tresorerie, db):
    response = client.post(ACCOUNTS, json=payload(db, journal_sage=" bq1 "), headers=tresorerie)

    assert response.status_code == 201
    assert response.json()["journal_sage"] == "BQ1"


@pytest.mark.parametrize("journal", ["BQ-1", "TROPLONGJOURNAL"])
def test_invalid_journal_sage_gives_422(client, tresorerie, db, journal):
    response = client.post(ACCOUNTS, json=payload(db, journal_sage=journal), headers=tresorerie)

    assert response.status_code == 422


def test_journal_sage_used_by_another_active_account_is_refused(client, tresorerie, db):
    add(db, "SIMTIS", "AWB", journal_sage="BQ1")
    account = add(db, "SIMTIS", "CIH")

    response = client.put(
        f"{ACCOUNTS}/{account.id}",
        json=update_body(account, journal_sage="BQ1"),
        headers=tresorerie,
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Le journal Sage BQ1 est déjà celui du compte AWB MAD de cette société."
    }


def test_same_journal_in_another_company_is_accepted(client, tresorerie, db):
    add(db, "SOCX", "AWB", journal_sage="BQ1")
    account = add(db, "SIMTIS", "CIH")

    response = client.put(
        f"{ACCOUNTS}/{account.id}",
        json=update_body(account, journal_sage="BQ1"),
        headers=tresorerie,
    )

    assert response.status_code == 200


def test_journal_sage_change_is_audited(client, tresorerie, db):
    account = add(db, "SIMTIS", "CIH")

    client.put(
        f"{ACCOUNTS}/{account.id}",
        json=update_body(account, journal_sage="BQ3"),
        headers=tresorerie,
    )

    [entry] = audit(db, "modification_compte")
    assert entry.nouvelle_valeur == {"journal_sage": "BQ3"}


def test_reactivating_an_account_whose_journal_is_taken_is_refused(client, tresorerie, db):
    old = add(db, "SIMTIS", "AWB", journal_sage="BQ1", actif=False)
    add(db, "SIMTIS", "CIH", journal_sage="BQ1")

    response = client.patch(f"{ACCOUNTS}/{old.id}/status", json={"actif": True}, headers=tresorerie)

    assert response.status_code == 409
    assert "BQ1" in response.json()["detail"]


# --- Suppression d'un compte sans historique (08/10/2026) -----------------------------------------


def test_an_account_without_history_is_deleted_with_its_manual_balances(client, tresorerie, db):
    account = add(db, "SIMTIS", "CIH", actif=False)
    save(
        db,
        BankAccountBalance(
            bank_account_id=account.id,
            date_solde=date(2026, 10, 1),
            solde=Decimal("100"),
            source="Saisie",
        ),
    )
    account_id = account.id

    response = client.delete(f"{ACCOUNTS}/{account_id}", headers=tresorerie)

    assert response.status_code == 204, response.text
    db.expire_all()
    assert db.get(BankAccount, account_id) is None
    assert (
        db.scalars(
            select(BankAccountBalance).where(BankAccountBalance.bank_account_id == account_id)
        ).all()
        == []
    )
    [log] = audit(db, "suppression_compte")
    assert log.ancienne_valeur["numero"] == account.numero
    assert log.ancienne_valeur["soldes_saisis_effaces"] == 1


def test_an_account_with_history_can_only_be_deactivated(client, tresorerie, db):
    account = add(db, "SIMTIS", "CIH")
    save(db, BankStatement(bank_account_id=account.id))

    listed = client.get(
        ACCOUNTS, params={"company_id": account.company_id}, headers=tresorerie
    ).json()
    response = client.delete(f"{ACCOUNTS}/{account.id}", headers=tresorerie)

    assert next(a for a in listed if a["id"] == account.id)["a_historique"] is True
    assert response.status_code == 409
    assert "désactivé" in response.json()["detail"]
    assert db.get(BankAccount, account.id) is not None


def test_deleting_an_account_needs_the_permission(client, direction, db):
    account = add(db, "SIMTIS", "CIH")

    assert client.delete(f"{ACCOUNTS}/{account.id}", headers=direction).status_code == 403
    assert client.delete(f"{ACCOUNTS}/999999", headers=direction).status_code == 403
