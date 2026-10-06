"""Rapprochement 1→1 (P11) : lancement, décisions, lectures, permissions et audit."""

from datetime import date
from decimal import Decimal
from itertools import count

import pytest
from sqlalchemy import select

from app.models import (
    AccountingEntry,
    AuditLog,
    Bank,
    BankAccount,
    BankStatement,
    BankTransaction,
    Company,
    ReconciliationMatch,
)
from tests.helpers import bearer, build_account, login, make_auth_user, save

_seq = count(1)
JOUR = date(2026, 9, 24)
PERIODE = {"du": "2026-09-01", "au": "2026-09-30"}


@pytest.fixture
def comptable(client, reference) -> dict[str, str]:
    make_auth_user(reference, "COMPTABLE", email="comptable@example.com")
    return bearer(login(client, "comptable@example.com"))


@pytest.fixture
def direction(client, reference) -> dict[str, str]:
    make_auth_user(reference, "DIRECTION", email="direction@example.com")
    return bearer(login(client, "direction@example.com"))


def company(db, code: str = "SIMTIS") -> Company:
    return db.scalar(select(Company).filter_by(code=code))


def account(db, company_code: str = "SIMTIS", bank_code: str = "AWB") -> BankAccount:
    bank = db.scalar(select(Bank).filter_by(code=bank_code))
    return save(
        db, build_account(company(db, company_code), bank, numero=f"RIB-RAP-{next(_seq):06d}")
    )


def operation(db, compte: BankAccount, montant="50000", jour=JOUR, libelle="VIR ABC", **over):
    statement = db.scalar(select(BankStatement).filter_by(bank_account_id=compte.id))
    if statement is None:
        statement = save(db, BankStatement(bank_account_id=compte.id))
    montant = Decimal(montant)
    return save(
        db,
        BankTransaction(
            statement_id=statement.id,
            bank_account_id=compte.id,
            date_operation=jour,
            libelle=libelle,
            debit=max(-montant, Decimal(0)),
            credit=max(montant, Decimal(0)),
            montant=montant,
            hash_ligne=f"t{next(_seq)}",
            **over,
        ),
    )


def ecriture(
    db, compte: BankAccount, montant="-50000", jour=JOUR, libelle="Règlement ABC", **over
) -> AccountingEntry:
    """Au sens de Sage : un montant négatif est un crédit du compte banque (argent qui sort)."""
    montant = Decimal(montant)
    values = {"numero_piece": "REG458", "tiers": "ABC", **over}
    return save(
        db,
        AccountingEntry(
            company_id=compte.company_id,
            bank_account_id=compte.id,
            journal="BQ1",
            compte="5141",
            date_ecriture=jour,
            libelle=libelle,
            debit=max(-montant, Decimal(0)),
            credit=max(montant, Decimal(0)),
            montant=montant,
            hash_ligne=f"e{next(_seq)}",
            **values,
        ),
    )


def run(client, headers, db, code: str = "SIMTIS", **over):
    body = {"company_id": company(db, code).id, **PERIODE, **over}
    return client.post("/api/reconciliation/run", json=body, headers=headers)


def proposals(client, headers, db, **params):
    params = {"company_id": str(company(db).id), **params}
    return client.get("/api/reconciliation/proposals", params=params, headers=headers)


def statuses(db, *rows) -> list[str]:
    for row in rows:
        db.refresh(row)
    return [row.statut for row in rows]


def audit_actions(db) -> list[str]:
    return list(db.scalars(select(AuditLog.action).order_by(AuditLog.id)))


# --- Lancement du moteur --------------------------------------------------------------------------


def test_example_of_the_functional_architecture_is_proposed_then_validated(client, comptable, db):
    compte = account(db)
    tx = operation(db, compte)
    entry = ecriture(db, compte)

    response = run(client, comptable, db)

    assert response.status_code == 200, response.text
    assert response.json()["nb_propositions"] == 1
    assert statuses(db, tx, entry) == ["À vérifier", "À vérifier"]
    [proposal] = proposals(client, comptable, db).json()["correspondances"]
    assert (proposal["statut"], proposal["origine"], proposal["score"]) == (
        "Proposée",
        "Automatique",
        "60.00",
    )
    assert proposal["forte"] is False
    assert [(c["code"], c["points"]) for c in proposal["criteres"]] == [
        ("reference", "0.00"),
        ("montant", "30.00"),
        ("date", "15.00"),
        ("libelle", "10.00"),
        ("tiers", "5.00"),
    ]
    assert proposal["operation"]["id"] == tx.id
    assert proposal["ecriture"]["numero_piece"] == "REG458"

    validated = client.post(
        f"/api/reconciliation/matches/{proposal['id']}/validate", headers=comptable
    )

    assert validated.status_code == 200, validated.text
    assert validated.json()["statut"] == "Validée"
    assert validated.json()["valide_par"]
    assert statuses(db, tx, entry) == ["Rapprochée", "Rapprochée"]
    assert audit_actions(db)[-2:] == ["rapprochement_lance", "validation_rapprochement"]


def test_the_engine_never_validates_by_itself(client, comptable, db):
    compte = account(db)
    tx = operation(db, compte, libelle="VIR REG458 ABC")
    ecriture(db, compte)

    run(client, comptable, db)

    [proposal] = proposals(client, comptable, db).json()["correspondances"]
    assert proposal["score"] == "100.00"
    assert proposal["forte"] is True
    assert proposal["statut"] == "Proposée"
    assert statuses(db, tx) == ["À vérifier"]


def test_close_candidates_give_no_proposal_and_lines_to_check(client, comptable, db):
    compte = account(db)
    tx = operation(db, compte)
    first, second = ecriture(db, compte), ecriture(db, compte)

    body = run(client, comptable, db).json()

    assert (body["nb_propositions"], body["nb_operations_ambigues"]) == (0, 1)
    assert statuses(db, tx, first, second) == ["À vérifier"] * 3


def test_entries_of_another_company_are_never_compared(client, comptable, db):
    simtis, tefil = account(db, "SIMTIS"), account(db, "SOCX")
    tx = operation(db, simtis)
    ecriture(db, tefil)

    assert run(client, comptable, db).json()["nb_propositions"] == 0
    assert statuses(db, tx) == ["Non rapprochée"]


def test_entries_of_another_bank_account_are_not_compared(client, comptable, db):
    awb, bp = account(db, bank_code="AWB"), account(db, bank_code="BP")
    operation(db, awb)
    ecriture(db, bp)

    assert run(client, comptable, db).json()["nb_propositions"] == 0


def test_running_again_replaces_pending_proposals_and_keeps_decisions(client, comptable, db):
    compte = account(db)
    operation(db, compte, jour=date(2026, 9, 10))
    ecriture(db, compte, jour=date(2026, 9, 10))
    kept_tx = operation(db, compte, montant="700", libelle="VIR XYZ")
    ecriture(db, compte, montant="-700", libelle="Règlement XYZ", tiers="XYZ", numero_piece="P7")
    run(client, comptable, db)
    pending = proposals(client, comptable, db).json()["correspondances"]
    to_keep = next(p for p in pending if p["operation"]["id"] == kept_tx.id)
    client.post(f"/api/reconciliation/matches/{to_keep['id']}/validate", headers=comptable)

    second = run(client, comptable, db).json()

    assert second["nb_propositions"] == 1
    assert len(proposals(client, comptable, db).json()["correspondances"]) == 1
    validated = proposals(client, comptable, db, statut="Validée").json()["correspondances"]
    assert [p["id"] for p in validated] == [to_keep["id"]]


def test_rejected_pair_is_not_proposed_again(client, comptable, db):
    compte = account(db)
    tx = operation(db, compte)
    entry = ecriture(db, compte)
    run(client, comptable, db)
    [proposal] = proposals(client, comptable, db).json()["correspondances"]

    rejected = client.post(
        f"/api/reconciliation/matches/{proposal['id']}/reject",
        json={"commentaire": "Pas le même client"},
        headers=comptable,
    )

    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["statut"] == "Rejetée"
    assert statuses(db, tx, entry) == ["Non rapprochée", "Non rapprochée"]
    assert run(client, comptable, db).json()["nb_propositions"] == 0
    assert statuses(db, tx) == ["Non rapprochée"]


def test_run_checks_period_and_account(client, comptable, db):
    other = account(db, "SOCX")

    inverted = run(client, comptable, db, du="2026-09-30", au="2026-09-01")
    too_long = run(client, comptable, db, du="2025-01-01", au="2026-09-30")
    foreign = run(client, comptable, db, bank_account_id=other.id)

    assert inverted.status_code == 409
    assert too_long.status_code == 409
    assert foreign.status_code == 404


# --- Décisions -----------------------------------------------------------------------------------


def _proposed(client, headers, db, **over):
    compte = account(db)
    tx = operation(db, compte, **over)
    entry = ecriture(db, compte)
    run(client, headers, db)
    [proposal] = proposals(client, headers, db).json()["correspondances"]
    return proposal, tx, entry


def test_a_decision_needs_a_pending_proposal(client, comptable, db):
    proposal, _, _ = _proposed(client, comptable, db)
    url = f"/api/reconciliation/matches/{proposal['id']}"
    client.post(f"{url}/validate", headers=comptable)

    assert client.post(f"{url}/validate", headers=comptable).status_code == 409
    assert client.post(f"{url}/reject", headers=comptable).status_code == 409
    assert (
        client.post("/api/reconciliation/matches/999999/validate", headers=comptable).status_code
        == 404
    )


def test_cancelling_a_validated_match_needs_a_reason_and_frees_the_lines(client, comptable, db):
    proposal, tx, entry = _proposed(client, comptable, db)
    url = f"/api/reconciliation/matches/{proposal['id']}"

    pending = client.request("DELETE", url, json={"motif": "Erreur"}, headers=comptable)
    client.post(f"{url}/validate", headers=comptable)
    empty = client.request("DELETE", url, json={"motif": ""}, headers=comptable)
    blank = client.request("DELETE", url, json={"motif": "   "}, headers=comptable)
    cancelled = client.request(
        "DELETE", url, json={"motif": "Mauvaise écriture"}, headers=comptable
    )

    assert pending.status_code == 409
    assert empty.status_code == 422
    assert blank.status_code == 409
    assert cancelled.status_code == 200, cancelled.text
    assert (cancelled.json()["statut"], cancelled.json()["commentaire"]) == (
        "Annulée",
        "Mauvaise écriture",
    )
    assert statuses(db, tx, entry) == ["Non rapprochée", "Non rapprochée"]
    assert audit_actions(db)[-1] == "annulation_rapprochement"


def test_batch_validation_only_accepts_strong_matches(client, comptable, db):
    compte = account(db)
    strong_tx = operation(db, compte, libelle="VIR REG458 ABC")
    ecriture(db, compte)
    operation(db, compte, montant="700", jour=date(2026, 9, 10), libelle="VIR XYZ")
    ecriture(
        db,
        compte,
        montant="-700",
        jour=date(2026, 9, 10),
        libelle="XYZ",
        tiers="XYZ",
        numero_piece="P7",
    )
    run(client, comptable, db)
    pending = proposals(client, comptable, db).json()["correspondances"]
    strong = [p["id"] for p in pending if p["forte"]]
    weak = [p["id"] for p in pending if not p["forte"]]
    url = "/api/reconciliation/matches/validate-batch"

    refused = client.post(url, json={"ids": strong + weak}, headers=comptable)
    accepted = client.post(url, json={"ids": strong}, headers=comptable)

    assert (len(strong), len(weak)) == (1, 1)
    assert refused.status_code == 409
    assert accepted.status_code == 200, accepted.text
    assert accepted.json() == {"nb_validees": 1}
    assert statuses(db, strong_tx) == ["Rapprochée"]
    assert len(proposals(client, comptable, db).json()["correspondances"]) == 1


# --- Rapprochement manuel ------------------------------------------------------------------------


def manual(client, headers, tx, entry, **over):
    body = {"transaction_id": tx.id, "ecriture_id": entry.id, **over}
    return client.post("/api/reconciliation/matches", json=body, headers=headers)


def test_manual_match_is_validated_at_once(client, comptable, db):
    compte = account(db)
    tx = operation(db, compte, libelle="ONEE FACTURE")
    entry = ecriture(db, compte, jour=date(2026, 9, 20), libelle="Electricité", tiers=None)

    response = manual(client, comptable, tx, entry, commentaire="Facture de septembre")

    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["statut"], body["origine"], body["commentaire"]) == (
        "Validée",
        "Manuelle",
        "Facture de septembre",
    )
    assert statuses(db, tx, entry) == ["Rapprochée", "Rapprochée"]
    assert audit_actions(db)[-1] == "rapprochement_manuel"


def test_manual_match_refuses_different_amounts_companies_and_accounts(client, comptable, db):
    awb, bp, tefil = account(db), account(db, bank_code="BP"), account(db, "SOCX")
    tx = operation(db, awb)

    amount = manual(client, comptable, tx, ecriture(db, awb, montant="-49000"))
    same_sign = manual(client, comptable, tx, ecriture(db, awb, montant="50000"))
    other_account = manual(client, comptable, tx, ecriture(db, bp))
    other_company = manual(client, comptable, tx, ecriture(db, tefil))

    assert [r.status_code for r in (amount, same_sign, other_account, other_company)] == [409] * 4
    assert "deux sociétés" in other_company.json()["detail"]


def test_manual_match_replaces_a_pending_proposal(client, comptable, db):
    proposal, tx, proposed_entry = _proposed(client, comptable, db)
    chosen = ecriture(db, account_of(db, tx), jour=date(2026, 9, 23), libelle="Autre")

    response = manual(client, comptable, tx, chosen)

    assert response.status_code == 201, response.text
    replaced = db.get(ReconciliationMatch, proposal["id"])
    db.refresh(replaced)
    assert replaced.statut == "Rejetée"
    assert statuses(db, tx, chosen, proposed_entry) == [
        "Rapprochée",
        "Rapprochée",
        "Non rapprochée",
    ]


def test_manual_match_refuses_an_already_matched_line(client, comptable, db):
    compte = account(db)
    tx = operation(db, compte)
    first, second = ecriture(db, compte), ecriture(db, compte)
    manual(client, comptable, tx, first)

    response = manual(client, comptable, tx, second)

    assert response.status_code == 409
    assert "déjà rapprochée" in response.json()["detail"]


def account_of(db, tx: BankTransaction) -> BankAccount:
    return db.get(BankAccount, tx.bank_account_id)


# --- Lectures ------------------------------------------------------------------------------------


def test_transactions_pane_counts_statuses_and_shows_the_match(client, comptable, db):
    compte = account(db)
    tx = operation(db, compte)
    ecriture(db, compte)
    operation(db, compte, montant="-80", libelle="FRAIS")
    run(client, comptable, db)

    response = client.get(
        "/api/reconciliation/transactions",
        params={"company_id": company(db).id, "bank_account_id": compte.id},
        headers=comptable,
    )

    body = response.json()
    assert response.status_code == 200
    assert body["total"] == 2
    assert body["par_statut"] == {
        "Non rapprochée": 1,
        "À vérifier": 1,
        "Rapprochée": 0,
        "Écart": 0,
    }
    proposed = next(o for o in body["operations"] if o["id"] == tx.id)
    assert proposed["correspondance"]["statut"] == "Proposée"
    assert proposed["bank_code"] == "AWB"


def test_candidates_are_sorted_by_score(client, comptable, db):
    compte = account(db)
    tx = operation(db, compte)
    best = ecriture(db, compte)
    other = ecriture(db, compte, jour=date(2026, 9, 27), libelle="Divers", tiers=None)
    ecriture(db, compte, montant="50000")  # même sens : jamais candidate

    response = client.get(
        "/api/reconciliation/candidates", params={"transaction_id": tx.id}, headers=comptable
    )

    body = response.json()
    assert response.status_code == 200
    assert [c["ecriture"]["id"] for c in body["candidats"]] == [best.id, other.id]
    assert body["seuil_fort"] == "90.00"


# --- Permissions ---------------------------------------------------------------------------------


def test_consultation_can_read_but_not_decide(client, direction, db):
    compte = account(db)
    tx = operation(db, compte)
    entry = ecriture(db, compte)

    assert proposals(client, direction, db).status_code == 200
    assert run(client, direction, db).status_code == 403
    assert manual(client, direction, tx, entry).status_code == 403


def test_one_match_can_be_read_with_its_score_detail(client, direction, comptable, db):
    proposal, tx, _ = _proposed(client, comptable, db)

    response = client.get(f"/api/reconciliation/matches/{proposal['id']}", headers=direction)
    missing = client.get("/api/reconciliation/matches/999999", headers=direction)

    assert response.status_code == 200
    assert response.json()["operation"]["id"] == tx.id
    assert len(response.json()["criteres"]) == 5
    assert missing.status_code == 404


def test_a_proposal_with_different_amounts_cannot_be_validated(client, comptable, db):
    compte = account(db)
    tx = operation(db, compte, libelle="VIR REG458 ABC")
    entry = ecriture(db, compte, montant="-49000")
    run(client, comptable, db)
    [proposal] = proposals(client, comptable, db).json()["correspondances"]

    response = client.post(
        f"/api/reconciliation/matches/{proposal['id']}/validate", headers=comptable
    )

    assert proposal["criteres"][1] == {"code": "montant", "libelle": "Montant", "points": "0.00"}
    assert response.status_code == 409
    assert "Montant différent" in response.json()["detail"]
    assert statuses(db, tx, entry) == ["À vérifier", "À vérifier"]


# --- Historique ----------------------------------------------------------------------------------


def history(client, headers, db, **params):
    params = {"company_id": str(company(db).id), **params}
    return client.get("/api/reconciliation/history", params=params, headers=headers)


def test_history_lists_every_decision_with_who_and_when(client, comptable, direction, db):
    compte = account(db)
    for montant, jour in (("100", 10), ("200", 11), ("300", 12)):
        operation(db, compte, montant=montant, jour=date(2026, 9, jour), libelle=f"VIR {montant}")
        ecriture(
            db,
            compte,
            montant=f"-{montant}",
            jour=date(2026, 9, jour),
            libelle=f"VIR {montant}",
            numero_piece=f"P{montant}",
            tiers=None,
        )
    run(client, comptable, db)
    pending = {
        p["operation"]["montant"]: p["id"]
        for p in proposals(client, comptable, db).json()["correspondances"]
    }
    url = "/api/reconciliation/matches"
    client.post(f"{url}/{pending['100.00']}/validate", headers=comptable)
    client.post(f"{url}/{pending['200.00']}/reject", json={"commentaire": "Non"}, headers=comptable)
    client.post(f"{url}/{pending['300.00']}/validate", headers=comptable)
    client.request(
        "DELETE", f"{url}/{pending['300.00']}", json={"motif": "Erreur"}, headers=comptable
    )

    response = history(client, direction, db, **{"from": "2026-09-01", "to": "2026-09-30"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 3
    assert body["par_statut"] == {"Validée": 1, "Rejetée": 1, "Annulée": 1}
    # La plus récente d'abord : l'annulation a été décidée en dernier
    assert [d["statut"] for d in body["decisions"]] == ["Annulée", "Rejetée", "Validée"]
    assert all(d["decide_par"] and d["decide_le"] for d in body["decisions"])
    cancelled = body["decisions"][0]
    assert (cancelled["commentaire"], cancelled["valide_par"]) == (
        "Erreur",
        cancelled["decide_par"],
    )
    assert history(client, direction, db, statut="Rejetée").json()["total"] == 1
    assert proposals(client, comptable, db).json()["correspondances"] == []


def test_history_keeps_manual_matches_and_ignores_pending_proposals(client, comptable, db):
    compte = account(db)
    tx, entry = operation(db, compte, montant="900"), ecriture(db, compte, montant="-900")
    operation(db, compte)
    ecriture(db, compte)
    run(client, comptable, db)
    client.post(
        "/api/reconciliation/matches",
        json={"transaction_id": tx.id, "ecriture_id": entry.id},
        headers=comptable,
    )

    body = history(client, comptable, db).json()

    assert ("Manuelle", "Validée") in [(d["origine"], d["statut"]) for d in body["decisions"]]
    assert "Proposée" not in {d["statut"] for d in body["decisions"]}
    # Une proposition en attente n'est pas une décision : elle n'apparaît pas
    assert body["total"] == sum(body["par_statut"].values())


def test_history_never_mixes_companies_and_checks_rights(client, comptable, reference, db):
    tefil = account(db, "SOCX")
    tx, entry = operation(db, tefil, montant="900"), ecriture(db, tefil, montant="-900")
    client.post(
        "/api/reconciliation/matches",
        json={"transaction_id": tx.id, "ecriture_id": entry.id},
        headers=comptable,
    )
    make_auth_user(reference, email="sans-droit@example.com")
    no_right = bearer(login(client, "sans-droit@example.com"))

    assert history(client, comptable, db).json()["total"] == 0
    assert (
        history(client, comptable, db, company_id=str(company(db, "SOCX").id)).json()["total"] == 1
    )
    assert history(client, no_right, db).status_code == 403
