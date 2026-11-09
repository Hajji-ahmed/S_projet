"""Impayés Sage rapprochés avec l'écriture qu'ils annulent (type « E-E », 09/11/2026)."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import ReconciliationMatch
from app.services.reconciliation_annulations import PaireAnnulation, paires_annulation
from app.services.reconciliation_scoring import Ecriture
from tests.helpers import bearer, login, make_auth_user
from tests.test_reconciliation_api import (
    account,
    audit_actions,
    company,
    ecriture,
    operation,
    run,
    statuses,
)

URL = "/api/reconciliation/impayes-origines"


@pytest.fixture
def comptable(client, reference) -> dict[str, str]:
    make_auth_user(reference, "COMPTABLE", email="comptable@example.com")
    return bearer(login(client, "comptable@example.com"))


@pytest.fixture
def direction(client, reference) -> dict[str, str]:
    make_auth_user(reference, "DIRECTION", email="direction@example.com")
    return bearer(login(client, "direction@example.com"))


DU, AU = date(2026, 9, 1), date(2026, 9, 30)


def e(id_, jour, libelle, montant, compte=1) -> Ecriture:
    return Ecriture(
        id=id_,
        date_ecriture=jour,
        libelle=libelle,
        reference=None,
        numero_piece=None,
        tiers=None,
        montant=Decimal(montant),
        bank_account_id=compte,
    )


# --- Recherche des paires (fonctions pures) ------------------------------------------------------


def test_an_unpaid_cheque_is_paired_with_its_remittance():
    origine = e(1, date(2026, 9, 3), "EAR1° 0001006. HAJAR ISMAILI", "-10000")
    impaye = e(2, date(2026, 9, 5), "IMP EAR1° 0001006. HAJAR ISMAILI", "10000")

    assert paires_annulation([origine, impaye], du=DU, au=AU) == [
        PaireAnnulation(impaye_id=2, origine_id=1, ecart_jours=2)
    ]


def test_the_closest_earlier_origin_wins_and_a_later_one_never_counts():
    """ABS 2600098 : l'effet du 05/09 et sa représentation du 20/09 ; l'impayé du 09/09 annule
    celui d'avant ; un plus ancien (01/09) perd face au plus proche."""
    ancien = e(1, date(2026, 9, 1), "EAR° N° ABS 2600098 SABIR", "-20000")
    proche = e(2, date(2026, 9, 5), "EAR° N° ABS 2600098 SABIR", "-20000")
    apres = e(3, date(2026, 9, 20), "EAR° ABS2600098 SABIR", "-20000")
    impaye = e(4, date(2026, 9, 9), "IMP EAR° N° ABS 2600098 SABIR", "20000")

    [paire] = paires_annulation([ancien, proche, apres, impaye], du=DU, au=AU)

    assert (paire.impaye_id, paire.origine_id) == (4, 2)


def test_nothing_is_proposed_on_a_tie_or_a_shared_origin():
    impaye = e(9, date(2026, 9, 9), "IMP EAR1° 0012345 X", "500")
    egalite = [
        e(1, date(2026, 9, 5), "EAR1° 0012345 X", "-500"),
        e(2, date(2026, 9, 5), "EAR1° 0012345 Y", "-500"),
    ]
    assert paires_annulation([*egalite, impaye], du=DU, au=AU) == []

    origine = e(1, date(2026, 9, 5), "EAR1° 0012345 X", "-500")
    deux_impayes = [impaye, e(10, date(2026, 9, 10), "IMP EAR1° 0012345 X", "500")]
    assert paires_annulation([origine, *deux_impayes], du=DU, au=AU) == []


def test_amount_account_number_type_and_period_are_required():
    impaye = e(9, date(2026, 9, 9), "IMP EAR1° 0012345 X", "500")
    refusees = [
        e(1, date(2026, 9, 5), "EAR1° 0012345 X", "-499.99"),  # montant différent
        e(2, date(2026, 9, 5), "EAR1° 0012345 X", "500"),  # même sens
        e(3, date(2026, 9, 5), "EAR1° 0012345 X", "-500", compte=2),  # autre compte
        e(4, date(2026, 9, 5), "EAR1° 0099999 X", "-500"),  # autre n°
        e(5, date(2026, 9, 5), "VIR 0012345 X", "-500"),  # ni chèque ni effet
    ]
    assert paires_annulation([*refusees, impaye], du=DU, au=AU) == []

    origine = e(1, date(2026, 8, 5), "EAR1° 0012345 X", "-500")
    hors_periode = e(9, date(2026, 8, 9), "IMP EAR1° 0012345 X", "500")
    assert paires_annulation([origine, hors_periode], du=DU, au=AU) == []


# --- Lancement, décisions et lectures (API) ------------------------------------------------------


def _paire(db):
    compte = account(db)
    origine = ecriture(
        db, compte, "-10000", date(2026, 9, 3), "EAR1° 0001006. HAJAR ISMAILI", numero_piece=None
    )
    impaye = ecriture(
        db, compte, "10000", date(2026, 9, 5), "IMP EAR1° 0001006. HAJAR ISMAILI", numero_piece=None
    )
    return compte, origine, impaye


def paires(client, headers, db, **params):
    params = {"company_id": str(company(db).id), **params}
    return client.get(URL, params=params, headers=headers)


def test_run_proposes_the_pair_which_a_human_validates_with_a_code(client, comptable, db):
    _, origine, impaye = _paire(db)

    result = run(client, comptable, db).json()
    [paire] = paires(client, comptable, db).json()["paires"]

    assert result["nb_annulations"] == 1
    assert (paire["statut"], paire["impaye"]["id"], paire["origine"]["id"]) == (
        "Proposée",
        impaye.id,
        origine.id,
    )
    assert paire["ecart_jours"] == 2
    assert statuses(db, origine, impaye) == ["À vérifier", "À vérifier"]

    response = client.post(
        "/api/reconciliation/matches/validate-batch", json={"ids": [paire["id"]]}, headers=comptable
    )

    assert response.status_code == 200, response.text
    assert statuses(db, origine, impaye) == ["Rapprochée", "Rapprochée"]
    [validee] = paires(client, comptable, db, statut="Validée").json()["paires"]
    assert validee["code"].startswith(f"AWB-{date.today().year % 100:02d}-")
    assert validee["valide_par"] is not None
    assert audit_actions(db)[-1] == "validation_rapprochement"
    # Pas d'opération de banque : jamais dans les propositions banque ↔ Sage
    proposals = client.get(
        "/api/reconciliation/proposals",
        params={"company_id": str(company(db).id), "statut": "Validée"},
        headers=comptable,
    ).json()["correspondances"]
    assert proposals == []
    detail = client.get(f"/api/reconciliation/matches/{paire['id']}", headers=comptable)
    assert detail.status_code == 409


def test_only_entries_left_free_by_the_bank_are_paired(client, comptable, db):
    """« Seulement les restes » : une origine déjà rapprochée avec une opération de banque n'est
    pas reprise pour un impayé."""
    compte, origine, impaye = _paire(db)
    tx = operation(db, compte, "10000", date(2026, 9, 3), "OPERATION DIVERSE")
    manuel = client.post(
        "/api/reconciliation/matches",
        json={"transaction_id": tx.id, "ecriture_id": origine.id},
        headers=comptable,
    )
    assert manuel.status_code == 201, manuel.text

    result = run(client, comptable, db).json()

    assert result["nb_annulations"] == 0
    assert paires(client, comptable, db).json()["paires"] == []
    assert statuses(db, impaye) == ["Non rapprochée"]


def test_running_again_replaces_a_pending_pair(client, comptable, db):
    _paire(db)
    run(client, comptable, db)

    result = run(client, comptable, db).json()

    assert result["nb_annulations"] == 1
    assert len(paires(client, comptable, db).json()["paires"]) == 1
    assert len(list(db.scalars(select(ReconciliationMatch).filter_by(type="E-E")))) == 1


def test_a_rejected_pair_frees_both_entries(client, comptable, db):
    _, origine, impaye = _paire(db)
    run(client, comptable, db)
    [paire] = paires(client, comptable, db).json()["paires"]

    response = client.post(
        "/api/reconciliation/matches/reject-batch", json={"ids": [paire["id"]]}, headers=comptable
    )

    assert response.status_code == 200
    assert statuses(db, origine, impaye) == ["Non rapprochée", "Non rapprochée"]


def test_cancelling_a_validated_pair_needs_a_reason(client, comptable, db):
    _, origine, impaye = _paire(db)
    run(client, comptable, db)
    [paire] = paires(client, comptable, db).json()["paires"]
    client.post(
        "/api/reconciliation/matches/validate-batch", json={"ids": [paire["id"]]}, headers=comptable
    )
    url = f"{URL}/{paire['id']}"

    vide = client.request("DELETE", url, json={"motif": ""}, headers=comptable)
    annulee = client.request("DELETE", url, json={"motif": "Effet représenté"}, headers=comptable)

    assert vide.status_code == 422
    assert annulee.status_code == 200, annulee.text
    assert (annulee.json()["statut"], annulee.json()["commentaire"]) == (
        "Annulée",
        "Effet représenté",
    )
    assert statuses(db, origine, impaye) == ["Non rapprochée", "Non rapprochée"]
    assert audit_actions(db)[-1] == "annulation_rapprochement"
    autre = client.request("DELETE", f"{URL}/999999", json={"motif": "x"}, headers=comptable)
    assert autre.status_code == 404


def test_consultation_reads_but_cannot_decide(client, direction, comptable, db):
    _paire(db)
    run(client, comptable, db)
    [paire] = paires(client, direction, db).json()["paires"]

    response = client.post(
        "/api/reconciliation/matches/validate-batch", json={"ids": [paire["id"]]}, headers=direction
    )
    cancel = client.request(
        "DELETE", f"{URL}/{paire['id']}", json={"motif": "x"}, headers=direction
    )

    assert response.status_code == 403
    assert cancel.status_code == 403
    assert client.get(URL, params={"company_id": str(company(db).id)}).status_code == 401


def test_pairs_are_read_per_company(client, comptable, db):
    _paire(db)
    run(client, comptable, db)

    autre = client.get(URL, params={"company_id": str(company(db, "SOCX").id)}, headers=comptable)

    assert autre.json()["paires"] == []
