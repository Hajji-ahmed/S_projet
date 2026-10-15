"""Historique (P16.2) : journal d'audit filtrable, résumé, détail avant / après, permission."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models import AuditLog
from app.services import audit_service
from app.services.historique_service import ACTIONS, differences, libelle_action, resume
from tests.helpers import bearer, login, make_auth_user


@pytest.fixture
def responsable(client, reference):
    user = make_auth_user(reference, "RESPONSABLE", nom="Mustapha", email="m@example.com")
    return user, bearer(login(client, "m@example.com"))


def ecrire(db, user_id, action, entite="reconciliation_match", entite_id=1, **valeurs):
    """Ligne de journal ; `le` fixe sa date dès l'insertion (audit_logs refuse toute mise à jour)."""
    if "le" not in valeurs:
        return audit_service.log(
            db,
            user_id=user_id,
            action=action,
            entite=entite,
            entite_id=entite_id,
            avant=valeurs.get("avant"),
            apres=valeurs.get("apres"),
        )
    entry = AuditLog(
        user_id=user_id,
        action=action,
        entite=entite,
        entite_id=str(entite_id),
        created_at=valeurs["le"],
    )
    db.add(entry)
    db.flush()
    return entry


# --- Règles pures ---------------------------------------------------------------------------------


def test_a_line_summary_shows_the_useful_values_and_the_status_change():
    assert (
        resume(
            {"code": None, "statut": "Proposée", "score": "89.17"},
            {"code": "BP-26-000123", "statut": "Validée", "score": "89.17"},
        )
        == "BP-26-000123 — Proposée → Validée"
    )
    assert resume(None, {"fichier_nom": "RLV_Bp.xlsx", "nb_lignes": 3}) == "RLV_Bp.xlsx"
    assert resume(None, None) == ""


def test_differences_list_every_field_and_flag_the_changed_ones():
    diff = differences(
        {"statut": "En cours", "montant": "10"}, {"statut": "Traité", "montant": "10"}
    )

    assert [(d.champ, d.modifie) for d in diff] == [("statut", True), ("montant", False)]


def test_unknown_actions_stay_readable():
    assert libelle_action("validation_rapprochement") == "Validation rapprochement"
    assert libelle_action("suppression_releve_awb") == "Suppression releve awb"


@pytest.mark.parametrize(
    "action",
    ["import_releve", "validation_rapprochement", "modification_permissions", "cloture_ecart"],
)
def test_actions_required_by_the_cdc_have_a_french_label(action):
    """CDC §11 : ces actions sont toujours journalisées (tests de chaque module) et lisibles."""
    assert action in ACTIONS


# --- API ------------------------------------------------------------------------------------------


def test_the_journal_lists_newest_first_with_who_and_a_summary(client, responsable, db):
    me, headers = responsable
    ecrire(db, me.id, "rapprochement_lance", apres={"nb_propositions": 3})
    ecrire(
        db,
        me.id,
        "validation_rapprochement",
        avant={"statut": "Proposée"},
        apres={"statut": "Validée", "code": "BP-26-000001"},
    )
    ecrire(db, None, "repointage", entite="bank_transaction", apres={"pointage": "COM"})

    body = client.get("/api/audit", headers=headers).json()

    premieres = [i for i in body["items"] if i["action"] != "connexion"][:3]
    assert [i["action_libelle"] for i in premieres] == [
        "Repointage",
        "Validation rapprochement",
        "Rapprochement lancé",
    ]
    assert premieres[0]["utilisateur"] is None
    assert premieres[1]["utilisateur"] == "Mustapha"
    assert premieres[1]["resume"] == "BP-26-000001 — Proposée → Validée"
    assert premieres[1]["entite_libelle"] == "Rapprochement"
    assert "avant" not in premieres[1]


def test_filters_by_user_action_entity_and_moroccan_day(client, responsable, db):
    me, headers = responsable
    ecrire(
        db, me.id, "cloture_ecart", entite="discrepancy", le=datetime(2026, 9, 1, 12, tzinfo=UTC)
    )
    ecrire(
        db, me.id, "cloture_ecart", entite="discrepancy", le=datetime(2026, 9, 3, 12, tzinfo=UTC)
    )
    ecrire(db, None, "cloture_ecart", entite="discrepancy", le=datetime(2026, 9, 3, 13, tzinfo=UTC))

    def total(**params):
        response = client.get("/api/audit", params=params, headers=headers)
        assert response.status_code == 200, response.text
        return response.json()["total"]

    assert total(action="cloture_ecart") == 3
    assert total(action="cloture_ecart", user_id=me.id) == 2
    assert total(entite="discrepancy", **{"from": "2026-09-02", "to": "2026-09-03"}) == 2
    assert total(entite="discrepancy", **{"from": "2026-09-01", "to": "2026-09-01"}) == 1
    refus = client.get(
        "/api/audit", params={"from": "2026-09-03", "to": "2026-09-01"}, headers=headers
    )
    assert refus.status_code == 409


def test_pages_hold_fifty_entries(client, responsable, db):
    me, headers = responsable
    for n in range(55):
        ecrire(db, me.id, "export_lettrage", entite_id=n)

    page2 = client.get(
        "/api/audit", params={"action": "export_lettrage", "page": 2}, headers=headers
    ).json()

    assert (page2["total"], page2["pages"], len(page2["items"])) == (55, 2, 5)


def test_the_detail_shows_before_and_after_field_by_field(client, responsable, db):
    me, headers = responsable
    entry = ecrire(
        db,
        me.id,
        "modification_permissions",
        entite="role",
        avant={"nom": "Direction", "permissions": ["dashboard.view"]},
        apres={"nom": "Direction", "permissions": ["audit.view", "dashboard.view"]},
    )

    detail = client.get(f"/api/audit/{entry.id}", headers=headers).json()

    assert detail["action_libelle"] == "Modification de rôle ou de permissions"
    assert detail["differences"] == [
        {"champ": "nom", "avant": "Direction", "apres": "Direction", "modifie": False},
        {
            "champ": "permissions",
            "avant": ["dashboard.view"],
            "apres": ["audit.view", "dashboard.view"],
            "modifie": True,
        },
    ]
    assert client.get("/api/audit/999999999", headers=headers).status_code == 404


def test_filter_options_come_from_the_journal(client, responsable, db):
    me, headers = responsable
    ecrire(db, me.id, "action_inconnue_test", entite="chose_test")

    body = client.get("/api/audit/filtres", headers=headers).json()

    assert {"code": "action_inconnue_test", "libelle": "Action inconnue test", "nb": 1} in body[
        "actions"
    ]
    assert {"code": "chose_test", "libelle": "Chose test", "nb": None} in body["entites"]
    assert {"id": me.id, "nom": "Mustapha"} in body["utilisateurs"]


def test_the_journal_needs_audit_view_and_stays_read_only(client, reference, db):
    make_auth_user(reference, "COMPTABLE", email="compta@example.com")
    headers = bearer(login(client, "compta@example.com"))

    assert client.get("/api/audit", headers=headers).status_code == 403
    assert client.get("/api/audit/filtres", headers=headers).status_code == 403
    assert db.scalar(select(AuditLog.id).limit(1)) is not None  # la connexion est journalisée
