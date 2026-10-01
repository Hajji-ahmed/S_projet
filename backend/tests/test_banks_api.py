"""Référentiel des banques : lecture, création, modification, activation, à travers l'API."""

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, Bank, Company
from app.seeds.reference import seed_reference
from tests.helpers import bearer, build_account, login, make_auth_user, save

BANKS = "/api/banks"


@pytest.fixture
def tresorerie(client, reference) -> dict[str, str]:
    make_auth_user(reference, "TRESORERIE", email="tresorerie@example.com")
    return bearer(login(client, "tresorerie@example.com"))


@pytest.fixture
def direction(client, reference) -> dict[str, str]:
    make_auth_user(reference, "DIRECTION", email="direction@example.com")
    return bearer(login(client, "direction@example.com"))


def bank(db, code: str) -> Bank:
    return db.scalar(select(Bank).filter_by(code=code))


def audit_entries(db, action: str) -> list[AuditLog]:
    return list(db.scalars(select(AuditLog).filter_by(action=action).order_by(AuditLog.id)))


def add_account(db, bank_code: str, *, actif: bool = True):
    company = db.scalar(select(Company).filter_by(code="SIMTIS"))
    return save(db, build_account(company, bank(db, bank_code), actif=actif))


# --- Lecture -------------------------------------------------------------------------------------


def test_list_follows_the_workbook_order(client, direction):
    response = client.get(BANKS, headers=direction)

    assert response.status_code == 200
    assert [item["code"] for item in response.json()] == ["AWB", "BMCE", "BP", "CIH", "BMCI"]
    assert response.json()[0] == {
        "id": response.json()[0]["id"],
        "code": "AWB",
        "nom": "Attijariwafa",
        "logo": "/banques/attijariwafa.png",
        "ordre_affichage": 1,
        "actif": True,
        "nb_comptes_actifs": 0,
    }


def test_list_counts_only_active_accounts(client, direction, db):
    add_account(db, "CIH")
    add_account(db, "CIH")
    add_account(db, "CIH", actif=False)

    counts = {
        item["code"]: item["nb_comptes_actifs"]
        for item in client.get(BANKS, headers=direction).json()
    }

    assert counts["CIH"] == 2
    assert counts["AWB"] == 0


def test_list_includes_inactive_banks(client, tresorerie, db):
    client.patch(f"{BANKS}/{bank(db, 'BMCI').id}/status", json={"actif": False}, headers=tresorerie)

    items = {item["code"]: item for item in client.get(BANKS, headers=tresorerie).json()}

    assert items["BMCI"]["actif"] is False


def test_get_one_bank(client, direction, db):
    response = client.get(f"{BANKS}/{bank(db, 'BP').id}", headers=direction)

    assert response.status_code == 200
    assert response.json()["code"] == "BP"


def test_unknown_bank_gives_404(client, direction):
    response = client.get(f"{BANKS}/999999", headers=direction)

    assert response.status_code == 404
    assert response.json() == {"detail": "Banque introuvable."}


# --- Création ------------------------------------------------------------------------------------


def test_create_bank(client, tresorerie, db):
    response = client.post(
        BANKS, json={"code": " cdm ", "nom": "  Crédit du Maroc ", "logo": None}, headers=tresorerie
    )

    assert response.status_code == 201
    body = response.json()
    assert (body["code"], body["nom"], body["actif"], body["nb_comptes_actifs"]) == (
        "CDM",
        "Crédit du Maroc",
        True,
        0,
    )
    assert body["ordre_affichage"] == 6  # après BMCI (5)


def test_create_bank_is_audited(client, tresorerie, db):
    client.post(BANKS, json={"code": "CDM", "nom": "Crédit du Maroc"}, headers=tresorerie)

    [entry] = audit_entries(db, "creation_banque")
    assert entry.entite == "bank"
    assert entry.nouvelle_valeur == {
        "code": "CDM",
        "nom": "Crédit du Maroc",
        "logo": None,
        "ordre_affichage": 6,
        "actif": True,
    }
    assert entry.user_id is not None and entry.ip


def test_duplicate_code_gives_409(client, tresorerie):
    response = client.post(BANKS, json={"code": "awb", "nom": "Doublon"}, headers=tresorerie)

    assert response.status_code == 409
    assert response.json() == {"detail": "Le code AWB est déjà utilisé par une autre banque."}


@pytest.mark.parametrize(
    "payload",
    [
        {"code": "A", "nom": "Trop court"},
        {"code": "TROPLONGCODE", "nom": "Trop long"},
        {"code": "AB-C", "nom": "Caractère interdit"},
        {"code": "OK1", "nom": " "},
        {"code": "OK1", "nom": "Logo externe", "logo": "https://exemple.com/logo.png"},
        {"code": "OK1", "nom": "Logo hors dossier", "logo": "/banques/../logo-simtis.png"},
        {"code": "OK1", "nom": "Ordre négatif", "ordre_affichage": -1},
        {"code": "OK1", "nom": "Champ inconnu", "couleur": "rouge"},
    ],
)
def test_invalid_creation_gives_422(client, tresorerie, payload, db):
    before = db.scalar(select(func.count()).select_from(Bank))

    assert client.post(BANKS, json=payload, headers=tresorerie).status_code == 422
    assert db.scalar(select(func.count()).select_from(Bank)) == before


def test_logo_from_the_banks_folder_is_accepted(client, tresorerie):
    response = client.post(
        BANKS,
        json={"code": "CDM", "nom": "Crédit du Maroc", "logo": "/banques/cih.png"},
        headers=tresorerie,
    )

    assert response.status_code == 201
    assert response.json()["logo"] == "/banques/cih.png"


# --- Modification --------------------------------------------------------------------------------


def test_update_bank(client, tresorerie, db):
    bmci = bank(db, "BMCI")

    response = client.put(
        f"{BANKS}/{bmci.id}",
        json={"nom": "BMCI Groupe BNP Paribas", "logo": "/banques/bmci.png", "ordre_affichage": 9},
        headers=tresorerie,
    )

    assert response.status_code == 200
    assert response.json()["nom"] == "BMCI Groupe BNP Paribas"
    assert response.json()["ordre_affichage"] == 9


def test_update_audits_only_the_changed_fields(client, tresorerie, db):
    bmci = bank(db, "BMCI")

    client.put(
        f"{BANKS}/{bmci.id}",
        json={"nom": "Nouveau nom", "logo": bmci.logo, "ordre_affichage": bmci.ordre_affichage},
        headers=tresorerie,
    )

    [entry] = audit_entries(db, "modification_banque")
    assert entry.ancienne_valeur == {"nom": "BMCI"}
    assert entry.nouvelle_valeur == {"nom": "Nouveau nom"}


def test_update_without_change_writes_no_audit(client, tresorerie, db):
    bp = bank(db, "BP")

    response = client.put(
        f"{BANKS}/{bp.id}",
        json={"nom": bp.nom, "logo": bp.logo, "ordre_affichage": bp.ordre_affichage},
        headers=tresorerie,
    )

    assert response.status_code == 200
    assert audit_entries(db, "modification_banque") == []


def test_code_cannot_be_changed(client, tresorerie, db):
    awb = bank(db, "AWB")

    response = client.put(
        f"{BANKS}/{awb.id}",
        json={"code": "ATW", "nom": "Attijariwafa", "logo": None, "ordre_affichage": 1},
        headers=tresorerie,
    )

    assert response.status_code == 422
    db.refresh(awb)
    assert awb.code == "AWB"


def test_update_unknown_bank_gives_404(client, tresorerie):
    response = client.put(
        f"{BANKS}/999999",
        json={"nom": "Xx", "logo": None, "ordre_affichage": 1},
        headers=tresorerie,
    )

    assert response.status_code == 404


# --- Activation / désactivation ------------------------------------------------------------------


def test_deactivate_a_bank_without_accounts(client, tresorerie, db):
    bmci = bank(db, "BMCI")

    response = client.patch(f"{BANKS}/{bmci.id}/status", json={"actif": False}, headers=tresorerie)

    assert response.status_code == 200
    assert response.json()["actif"] is False
    [entry] = audit_entries(db, "desactivation_banque")
    assert (entry.ancienne_valeur, entry.nouvelle_valeur) == ({"actif": True}, {"actif": False})


def test_a_bank_with_active_accounts_cannot_be_deactivated(client, tresorerie, db):
    add_account(db, "CIH")
    add_account(db, "CIH")
    cih = bank(db, "CIH")

    response = client.patch(f"{BANKS}/{cih.id}/status", json={"actif": False}, headers=tresorerie)

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Impossible de désactiver CIH : 2 comptes actifs. Désactivez d'abord ses comptes."
    }
    db.refresh(cih)
    assert cih.actif is True
    assert audit_entries(db, "desactivation_banque") == []


def test_inactive_accounts_do_not_block_deactivation(client, tresorerie, db):
    add_account(db, "BP", actif=False)

    response = client.patch(
        f"{BANKS}/{bank(db, 'BP').id}/status", json={"actif": False}, headers=tresorerie
    )

    assert response.status_code == 200


def test_reactivate_a_bank(client, tresorerie, db):
    bmci = bank(db, "BMCI")
    client.patch(f"{BANKS}/{bmci.id}/status", json={"actif": False}, headers=tresorerie)

    response = client.patch(f"{BANKS}/{bmci.id}/status", json={"actif": True}, headers=tresorerie)

    assert response.json()["actif"] is True
    assert len(audit_entries(db, "reactivation_banque")) == 1


def test_setting_the_same_status_writes_no_audit(client, tresorerie, db):
    response = client.patch(
        f"{BANKS}/{bank(db, 'BP').id}/status", json={"actif": True}, headers=tresorerie
    )

    assert response.status_code == 200
    assert audit_entries(db, "reactivation_banque") == []


def test_a_deactivated_bank_is_not_recreated_by_the_seeds(client, tresorerie, db):
    client.patch(f"{BANKS}/{bank(db, 'BMCI').id}/status", json={"actif": False}, headers=tresorerie)

    seed_reference(db)

    assert db.scalar(select(func.count()).select_from(Bank).filter_by(code="BMCI")) == 1
    assert bank(db, "BMCI").actif is False


# --- Permissions ---------------------------------------------------------------------------------


def test_direction_reads_but_cannot_write(client, direction, db):
    bp = bank(db, "BP")
    writes = [
        client.post(BANKS, json={"code": "CDM", "nom": "Crédit du Maroc"}, headers=direction),
        client.put(
            f"{BANKS}/{bp.id}",
            json={"nom": "Pirate", "logo": None, "ordre_affichage": 1},
            headers=direction,
        ),
        client.patch(f"{BANKS}/{bp.id}/status", json={"actif": False}, headers=direction),
    ]

    assert client.get(BANKS, headers=direction).status_code == 200
    assert [response.status_code for response in writes] == [403, 403, 403]
    db.refresh(bp)
    assert (bp.nom, bp.actif) == ("BP", True)
    assert bank(db, "CDM") is None


def test_anonymous_access_is_refused(client, reference):
    assert client.get(BANKS).status_code == 401
    assert client.post(BANKS, json={"code": "CDM", "nom": "Crédit du Maroc"}).status_code == 401
