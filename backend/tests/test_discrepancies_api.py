"""Écarts (P12) : création, génération, cycle de vie, clôture, lectures, permissions et audit."""

from datetime import date

import pytest
from sqlalchemy import select

from app.models import AuditLog, Discrepancy, User
from app.services import discrepancy_service
from tests.helpers import bearer, login, make_auth_user
from tests.test_reconciliation_api import (
    account,
    company,
    ecriture,
    operation,
    proposals,
    run,
    statuses,
)

URL = "/api/discrepancies"
# Dates passées depuis longtemps : la règle des 10 jours ne dépend pas du jour du test
JOUR = date(2025, 9, 24)
PERIODE = {"du": "2025-09-01", "au": "2025-09-30"}


@pytest.fixture
def comptable(client, reference) -> dict[str, str]:
    make_auth_user(reference, "COMPTABLE", email="comptable@example.com")
    return bearer(login(client, "comptable@example.com"))


@pytest.fixture
def direction(client, reference) -> dict[str, str]:
    make_auth_user(reference, "DIRECTION", email="direction@example.com")
    return bearer(login(client, "direction@example.com"))


def create(client, headers, type_ecart, tx=None, entry=None, **over):
    body = {
        "type": type_ecart,
        "transaction_id": tx.id if tx else None,
        "ecriture_id": entry.id if entry else None,
        **over,
    }
    return client.post(URL, json=body, headers=headers)


def generate(client, headers, db, **over):
    body = {"company_id": company(db).id, **PERIODE, **over}
    return client.post(f"{URL}/generate", json=body, headers=headers)


def listing(client, headers, db, **params):
    return client.get(URL, params={"company_id": company(db).id, **params}, headers=headers)


def patch(client, headers, ecart_id, **body):
    return client.patch(f"{URL}/{ecart_id}", json=body, headers=headers)


def close(client, headers, ecart_id, commentaire="Frais passés dans Sage"):
    return client.post(
        f"{URL}/{ecart_id}/close", json={"commentaire": commentaire}, headers=headers
    )


# --- Création manuelle ----------------------------------------------------------------------------


def test_amount_difference_is_recorded_with_its_lines(client, comptable, db):
    compte = account(db)
    tx = operation(db, compte, montant="12500", jour=JOUR)
    entry = ecriture(db, compte, montant="-12450", jour=JOUR)

    response = create(client, comptable, "Montant différent", tx, entry, commentaire="À voir")

    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["type"], body["statut"], body["montant"], body["difference"]) == (
        "Montant différent",
        "À traiter",
        "12500.00",
        "50.00",
    )
    assert (body["devise"], body["bank_code"], body["date_ecart"]) == ("MAD", "AWB", "2025-09-24")
    assert body["operation"]["id"] == tx.id and body["ecriture"]["id"] == entry.id
    assert statuses(db, tx, entry) == ["Écart", "Écart"]
    assert [event["action"] for event in body["historique"]] == ["creation_ecart"]


def test_each_type_requires_its_lines(client, comptable, db):
    compte = account(db)
    tx, entry = operation(db, compte, jour=JOUR), ecriture(db, compte, jour=JOUR)

    refused = [
        create(client, comptable, "Banque sans écriture"),
        create(client, comptable, "Banque sans écriture", tx, entry),
        create(client, comptable, "Écriture sans banque", tx),
        create(client, comptable, "Montant différent", tx),
        create(client, comptable, "Date différente", None, entry),
        create(client, comptable, "Libellé ambigu", None, entry),
        create(client, comptable, "Doublon potentiel", tx, entry),
        create(client, comptable, "Doublon potentiel"),
    ]

    assert [r.status_code for r in refused] == [409] * len(refused)
    assert create(client, comptable, "Doublon potentiel", None, entry).status_code == 201


def test_balanced_amounts_are_not_an_amount_difference(client, comptable, db):
    compte = account(db)
    tx, entry = operation(db, compte, jour=JOUR), ecriture(db, compte, jour=JOUR)

    response = create(client, comptable, "Montant différent", tx, entry)

    assert response.status_code == 409
    assert create(client, comptable, "Date différente", tx, entry).json()["difference"] == "0.00"


def test_lines_of_two_companies_or_accounts_are_refused(client, comptable, db):
    awb, bp, tefil = account(db), account(db, bank_code="BP"), account(db, "SOCX")
    tx = operation(db, awb, jour=JOUR)

    other_account = create(client, comptable, "Date différente", tx, ecriture(db, bp, jour=JOUR))
    other_company = create(client, comptable, "Date différente", tx, ecriture(db, tefil, jour=JOUR))

    assert other_account.status_code == 409
    assert other_company.status_code == 409


def test_a_line_has_only_one_open_discrepancy(client, comptable, db):
    tx = operation(db, account(db), jour=JOUR)
    create(client, comptable, "Banque sans écriture", tx)

    response = create(client, comptable, "Libellé ambigu", tx)

    assert response.status_code == 409
    assert "déjà un écart ouvert" in response.json()["detail"]


def test_a_pending_proposal_is_rejected_and_a_validated_match_blocks(client, comptable, db):
    compte = account(db)
    tx, entry = operation(db, compte), ecriture(db, compte)
    run(client, comptable, db)
    [proposal] = proposals(client, comptable, db).json()["correspondances"]

    response = create(client, comptable, "Libellé ambigu", tx, entry)

    assert response.status_code == 201, response.text
    assert proposals(client, comptable, db).json()["correspondances"] == []
    rejected = proposals(client, comptable, db, statut="Rejetée").json()["correspondances"]
    assert [p["id"] for p in rejected] == [proposal["id"]]

    other_tx, other_entry = (
        operation(db, compte, montant="900"),
        ecriture(db, compte, montant="-900"),
    )
    client.post(
        "/api/reconciliation/matches",
        json={"transaction_id": other_tx.id, "ecriture_id": other_entry.id},
        headers=comptable,
    )
    blocked = create(client, comptable, "Banque sans écriture", other_tx)
    assert blocked.status_code == 409
    assert "déjà rapprochée" in blocked.json()["detail"]


def test_lines_in_discrepancy_are_ignored_by_the_engine(client, comptable, db):
    compte = account(db)
    tx = operation(db, compte)
    ecriture(db, compte)
    create(client, comptable, "Banque sans écriture", tx)

    assert run(client, comptable, db).json()["nb_propositions"] == 0


def test_responsable_must_be_allowed_to_manage_discrepancies(client, comptable, reference, db):
    tx = operation(db, account(db), jour=JOUR)
    viewer = make_auth_user(reference, "DIRECTION", email="lecteur@example.com")
    manager = db.scalar(select(User).filter_by(email="comptable@example.com"))

    refused = create(client, comptable, "Banque sans écriture", tx, responsable_id=viewer.id)
    accepted = create(client, comptable, "Banque sans écriture", tx, responsable_id=manager.id)

    assert refused.status_code == 409
    assert accepted.status_code == 201
    assert accepted.json()["responsable"] == manager.nom


# --- Génération -----------------------------------------------------------------------------------


def test_generation_flags_lines_left_without_counterpart(client, comptable, db):
    compte = account(db)
    alone_tx = operation(db, compte, montant="300", jour=JOUR, libelle="FRAIS TENUE")
    alone_entry = ecriture(db, compte, montant="700", jour=JOUR, libelle="Remise chèques")
    matched_tx, matched_entry = operation(db, compte, jour=JOUR), ecriture(db, compte, jour=JOUR)
    client.post(
        "/api/reconciliation/matches",
        json={"transaction_id": matched_tx.id, "ecriture_id": matched_entry.id},
        headers=comptable,
    )

    response = generate(client, comptable, db)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["banque_sans_ecriture"], body["ecriture_sans_banque"], body["doublons"]) == (
        1,
        1,
        0,
    )
    assert statuses(db, alone_tx, alone_entry, matched_tx) == ["Écart", "Écart", "Rapprochée"]
    types = {e["type"] for e in listing(client, comptable, db).json()["ecarts"]}
    assert types == {"Banque sans écriture", "Écriture sans banque"}


def test_generation_waits_for_the_engine_window(db, reference):
    compte = account(db)
    user = make_auth_user(reference, "COMPTABLE", email="gen@example.com")
    recent = operation(db, compte, montant="300", jour=date(2025, 9, 25))
    old = operation(db, compte, montant="400", jour=date(2025, 9, 10))

    result = discrepancy_service.generate(
        db,
        company_id=compte.company_id,
        bank_account_id=None,
        date_from=date(2025, 9, 1),
        date_to=date(2025, 9, 30),
        acteur_id=user.id,
        ip=None,
        today=date(2025, 9, 30),
    )

    assert result.date_limite == date(2025, 9, 20)
    assert result.banque_sans_ecriture == 1
    assert statuses(db, recent, old) == ["Non rapprochée", "Écart"]


def test_generation_flags_duplicates_but_keeps_the_original(client, comptable, db):
    compte = account(db)
    first = operation(db, compte, montant="250", jour=JOUR, libelle="PRLV ONEE")
    twin = operation(db, compte, montant="250", jour=JOUR, libelle="prlv  onee")
    entry_a = ecriture(db, compte, montant="-80", jour=JOUR, libelle="Frais", numero_piece="F1")
    entry_b = ecriture(db, compte, montant="-80", jour=JOUR, libelle="FRAIS", numero_piece="F1")

    body = generate(client, comptable, db).json()

    assert body["doublons"] == 2
    ecarts = {
        (e["operation"] or e["ecriture"])["id"]: e["type"]
        for e in listing(client, comptable, db).json()["ecarts"]
    }
    assert ecarts[twin.id] == "Doublon potentiel"
    assert ecarts[entry_b.id] == "Doublon potentiel"
    # L'original reste une ligne sans pendant, signalée comme telle
    assert ecarts[first.id] == "Banque sans écriture"
    assert ecarts[entry_a.id] == "Écriture sans banque"


def test_a_line_that_already_had_a_discrepancy_is_never_flagged_again(client, comptable, db):
    tx = operation(db, account(db), montant="300", jour=JOUR)
    ecart = create(client, comptable, "Banque sans écriture", tx).json()
    close(client, comptable, ecart["id"])

    body = generate(client, comptable, db).json()

    assert body["total"] == 0
    assert statuses(db, tx) == ["Non rapprochée"]


def test_generation_checks_period(client, comptable, db):
    assert generate(client, comptable, db, du="2025-09-30", au="2025-09-01").status_code == 409
    assert generate(client, comptable, db, du="2024-01-01", au="2025-09-30").status_code == 409


# --- Cycle de vie ---------------------------------------------------------------------------------


@pytest.fixture
def ecart_id(client, comptable, db) -> int:
    tx = operation(db, account(db), montant="300", jour=JOUR)
    return create(client, comptable, "Banque sans écriture", tx).json()["id"]


def test_status_follows_the_lifecycle(client, comptable, ecart_id):
    skip = patch(client, comptable, ecart_id, statut="Traité")
    started = patch(client, comptable, ecart_id, statut="En cours")
    treated = patch(client, comptable, ecart_id, statut="Traité")
    back = patch(client, comptable, ecart_id, statut="En cours")
    closing_by_patch = patch(client, comptable, ecart_id, statut="Clôturé")

    assert skip.status_code == 409
    assert (started.status_code, started.json()["statut"]) == (200, "En cours")
    assert treated.json()["statut"] == "Traité" and treated.json()["traite_le"]
    assert back.json()["statut"] == "En cours" and back.json()["traite_le"] is None
    assert closing_by_patch.status_code == 422


def test_comment_and_responsable_can_change_and_are_traced(client, comptable, db, ecart_id):
    manager = db.scalar(select(User).filter_by(email="comptable@example.com"))

    assigned = patch(client, comptable, ecart_id, responsable_id=manager.id, commentaire="Relancer")
    cleared = patch(client, comptable, ecart_id, responsable_id=None)

    assert assigned.json()["responsable"] == manager.nom
    assert assigned.json()["commentaire"] == "Relancer"
    assert cleared.json()["responsable"] is None
    assert cleared.json()["commentaire"] == "Relancer"
    events = cleared.json()["historique"]
    assert [e["action"] for e in events] == [
        "creation_ecart",
        "modification_ecart",
        "modification_ecart",
    ]
    assert events[1]["avant"]["commentaire"] is None
    assert events[1]["apres"]["commentaire"] == "Relancer"


def test_closing_needs_a_comment_and_frees_the_lines(client, comptable, db):
    compte = account(db)
    tx, entry = operation(db, compte, montant="12500"), ecriture(db, compte, montant="-12450")
    ecart = create(client, comptable, "Montant différent", tx, entry).json()

    empty = client.post(f"{URL}/{ecart['id']}/close", json={"commentaire": ""}, headers=comptable)
    blank = close(client, comptable, ecart["id"], "   ")
    closed = close(client, comptable, ecart["id"], "Escompte de 50 DH passé dans Sage")

    assert empty.status_code == 422
    assert blank.status_code == 409
    assert closed.status_code == 200, closed.text
    body = closed.json()
    assert (body["statut"], body["commentaire"]) == ("Clôturé", "Escompte de 50 DH passé dans Sage")
    assert body["cloture_le"] and body["cloture_par"]
    assert statuses(db, tx, entry) == ["Non rapprochée", "Non rapprochée"]
    assert patch(client, comptable, ecart["id"], commentaire="x").status_code == 409
    assert close(client, comptable, ecart["id"]).status_code == 409
    assert db.scalar(select(AuditLog.action).order_by(AuditLog.id.desc())) == "cloture_ecart"


# --- Lectures -------------------------------------------------------------------------------------


def test_listing_counts_statuses_and_sums_open_amounts_per_currency(client, comptable, db):
    mad = account(db)
    eur = account(db, bank_code="BP")
    eur.devise = "EUR"
    db.flush()
    first = create(
        client, comptable, "Banque sans écriture", operation(db, mad, montant="300", jour=JOUR)
    )
    create(client, comptable, "Banque sans écriture", operation(db, mad, montant="-200", jour=JOUR))
    create(client, comptable, "Banque sans écriture", operation(db, eur, montant="50", jour=JOUR))
    closed = create(
        client, comptable, "Banque sans écriture", operation(db, mad, montant="999", jour=JOUR)
    )
    close(client, comptable, closed.json()["id"])
    patch(client, comptable, first.json()["id"], statut="En cours")

    body = listing(client, comptable, db).json()
    only_open = listing(client, comptable, db, statut="À traiter").json()

    assert body["total"] == 4
    assert body["par_statut"] == {"À traiter": 2, "En cours": 1, "Traité": 0, "Clôturé": 1}
    assert body["montants_ouverts"] == {"MAD": "500.00", "EUR": "50.00"}
    assert only_open["total"] == 2
    assert only_open["par_statut"] == body["par_statut"]


def test_listing_filters_by_type_and_search(client, comptable, db):
    compte = account(db)
    create(
        client,
        comptable,
        "Banque sans écriture",
        operation(db, compte, montant="1", jour=JOUR, libelle="PRLV ONEE"),
    )
    create(
        client,
        comptable,
        "Écriture sans banque",
        None,
        ecriture(db, compte, montant="5", jour=JOUR),
    )

    assert listing(client, comptable, db, type="Écriture sans banque").json()["total"] == 1
    assert listing(client, comptable, db, q="onee").json()["total"] == 1


def test_reconciliation_pane_shows_the_open_discrepancy(client, comptable, db):
    compte = account(db)
    tx = operation(db, compte, jour=JOUR)
    ecart = create(client, comptable, "Banque sans écriture", tx).json()

    body = client.get(
        "/api/reconciliation/transactions",
        params={"company_id": company(db).id},
        headers=comptable,
    ).json()

    assert body["operations"][0]["ecart_id"] == ecart["id"]
    assert body["par_statut"]["Écart"] == 1


def test_responsables_are_active_users_who_manage_discrepancies(client, comptable, reference, db):
    make_auth_user(reference, "DIRECTION", email="lecteur@example.com")
    make_auth_user(reference, "RESPONSABLE", email="resp@example.com", actif=False)

    response = client.get(
        f"{URL}/responsables", params={"company_id": company(db).id}, headers=comptable
    )

    emails = {db.get(User, item["id"]).email for item in response.json()}
    assert "comptable@example.com" in emails
    assert "lecteur@example.com" not in emails
    assert "resp@example.com" not in emails


def test_unknown_discrepancy_is_404(client, comptable):
    assert client.get(f"{URL}/999999", headers=comptable).status_code == 404


# --- Permissions ----------------------------------------------------------------------------------


def test_consultation_reads_but_does_not_manage(client, direction, comptable, db):
    tx = operation(db, account(db), jour=JOUR)
    ecart = create(client, comptable, "Banque sans écriture", tx).json()

    assert listing(client, direction, db).status_code == 200
    assert client.get(f"{URL}/{ecart['id']}", headers=direction).status_code == 200
    assert create(client, direction, "Libellé ambigu", tx).status_code == 403
    assert generate(client, direction, db).status_code == 403
    assert patch(client, direction, ecart["id"], statut="En cours").status_code == 403
    assert close(client, direction, ecart["id"]).status_code == 403
    assert db.get(Discrepancy, ecart["id"]).statut == "À traiter"
