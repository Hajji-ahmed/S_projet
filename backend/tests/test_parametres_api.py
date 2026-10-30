"""Paramètres (P16.3) : grille de rapprochement modifiable, modèles de mapping, permission."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import AuditLog, Bank, ColumnMapping, ReconciliationRule
from app.services import reconciliation_service
from tests.helpers import bearer, login, make_auth_user


@pytest.fixture
def admin(client, reference):
    make_auth_user(reference, "ADMIN", email="admin@example.com")
    return bearer(login(client, "admin@example.com"))


def envoyer(client, headers, *regles):
    return client.put(
        "/api/parametres/rapprochement", json={"regles": list(regles)}, headers=headers
    )


def test_the_grid_is_listed_in_screen_order(client, admin):
    body = client.get("/api/parametres/rapprochement", headers=admin).json()

    assert [r["code"] for r in body][:8] == [
        "REFERENCE",
        "MONTANT",
        "MONTANT_ROND",
        "DATE",
        "LIBELLE",
        "TIERS",
        "BONUS_SANS_REFERENCE",
        "FENETRE",
    ]
    assert {r["code"]: r["genre"] for r in body}["SEUIL_FORT"] == "seuil"
    # 28/10/2026 : le bonus des espèces, virements et autres se règle comme un critère
    assert {r["code"]: r["genre"] for r in body}["BONUS_SANS_REFERENCE"] == "critere"


def test_a_change_is_used_by_the_next_engine_run_and_audited(client, admin, db):
    response = envoyer(
        client,
        admin,
        {"code": "SEUIL_FORT", "poids": "85"},
        {"code": "DATE", "poids": "25", "tolerance": "5", "actif": True},
        {"code": "FENETRE", "poids": "0", "tolerance": "15"},
    )

    assert response.status_code == 200, response.text
    grille = reconciliation_service.grille(db)
    assert (grille.seuil_fort, grille.date, grille.tolerance_jours, grille.fenetre_jours) == (
        Decimal("85.00"),
        Decimal("25.00"),
        5,
        15,
    )
    audits = list(db.scalars(select(AuditLog).where(AuditLog.action == "modification_parametre")))
    assert sorted(a.nouvelle_valeur["code"] for a in audits) == ["DATE", "FENETRE", "SEUIL_FORT"]
    seuil = next(a for a in audits if a.nouvelle_valeur["code"] == "SEUIL_FORT")
    assert (seuil.ancienne_valeur["poids"], seuil.nouvelle_valeur["poids"]) == ("80.00", "85.00")


def test_an_unchanged_value_writes_no_audit(client, admin, db):
    envoyer(client, admin, {"code": "SEUIL_PROPOSITION", "poids": "50"})

    assert db.scalar(select(AuditLog).where(AuditLog.action == "modification_parametre")) is None


@pytest.mark.parametrize(
    ("regle", "message"),
    [
        ({"code": "LIBELLE", "poids": "120"}, "entre 0 et 100 points"),
        ({"code": "SEUIL_PROPOSITION", "poids": "0"}, "entre 1 et 100 points"),
        ({"code": "DATE", "poids": "30", "tolerance": "2.5"}, "nombre entier de jours"),
        ({"code": "FENETRE", "poids": "0", "tolerance": "0"}, "entre 1 et 60"),
        ({"code": "FENETRE_ELARGIE", "poids": "0", "tolerance": "400"}, "entre 31 et 366"),
        ({"code": "SEUIL_FORT", "poids": "40"}, "ne peut pas être inférieur"),
        ({"code": "MONTANT", "poids": "50", "actif": False}, "Montant doit rester actif"),
        ({"code": "MONTANT", "poids": "0"}, "Montant doit rester actif"),
    ],
)
def test_wrong_values_are_refused(client, admin, regle, message):
    response = envoyer(client, admin, regle)

    assert response.status_code == 409
    assert message in response.json()["detail"]


def test_a_refused_batch_changes_nothing(client, admin, db):
    response = envoyer(
        client,
        admin,
        {"code": "LIBELLE", "poids": "10"},
        {"code": "SEUIL_FORT", "poids": "500"},
    )

    assert response.status_code == 409
    libelle = db.scalar(select(ReconciliationRule).where(ReconciliationRule.code == "LIBELLE"))
    assert libelle.poids == Decimal("20.00")


def test_unknown_rules_are_refused(client, admin):
    assert envoyer(client, admin, {"code": "NOPE", "poids": "1"}).status_code == 404


def test_a_mapping_is_deleted_and_audited(client, admin, db):
    bank = db.scalar(select(Bank).where(Bank.code == "BP"))
    mapping = ColumnMapping(
        type="Banque", bank_id=bank.id, nom="BP", mapping={"date_operation": "Date"}
    )
    db.add(mapping)
    db.flush()

    listes = client.get("/api/parametres/mappings", headers=admin).json()
    supprime = client.delete(f"/api/parametres/mappings/{mapping.id}", headers=admin)

    assert {"banque": "BP", "nom": "BP"}.items() <= next(
        m for m in listes if m["id"] == mapping.id
    ).items()
    assert supprime.status_code == 204
    assert db.get(ColumnMapping, mapping.id) is None
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "suppression_mapping"))
    assert audit.ancienne_valeur["banque"] == "BP"
    assert client.delete(f"/api/parametres/mappings/{mapping.id}", headers=admin).status_code == 404


def test_settings_need_admin_settings(client, reference):
    make_auth_user(reference, "RESPONSABLE", email="resp@example.com")
    headers = bearer(login(client, "resp@example.com"))

    assert client.get("/api/parametres/rapprochement", headers=headers).status_code == 403
    assert envoyer(client, headers, {"code": "DATE", "poids": "1"}).status_code == 403
    assert client.get("/api/parametres/mappings", headers=headers).status_code == 403


def test_the_round_amount_points_are_a_setting(client, admin, db):
    """28/10/2026 : « Montant identique, sans centimes » (40) se règle comme un critère."""
    assert reconciliation_service.grille(db).montant == Decimal("60.00")
    response = envoyer(client, admin, {"code": "MONTANT_ROND", "poids": "35", "actif": True})

    assert response.status_code == 200, response.text
    assert reconciliation_service.grille(db).montant_rond == Decimal("35.00")


def test_the_bonus_without_reference_is_used_by_the_engine_grid(client, admin, db):
    """28/10/2026 : « BONUS_SANS_REFERENCE » (10 par défaut) se modifie à l'écran et désactivé
    vaut 0 dans la grille du moteur."""
    from app.services.reconciliation_service import grille

    assert grille(db).bonus_sans_reference == Decimal("10")

    response = envoyer(
        client, admin, {"code": "BONUS_SANS_REFERENCE", "poids": "15", "actif": True}
    )
    assert response.status_code == 200, response.text
    assert grille(db).bonus_sans_reference == Decimal("15")

    envoyer(client, admin, {"code": "BONUS_SANS_REFERENCE", "poids": "15", "actif": False})
    assert grille(db).bonus_sans_reference == Decimal("0")
