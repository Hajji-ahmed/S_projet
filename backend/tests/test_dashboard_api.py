"""Dashboard (P15, 14/10/2026) : KPI, évolution, frais, comptes, dernières opérations, alertes."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Bank
from app.services.dashboard_service import (
    alertes,
    categorie_frais,
    evolution,
    flux,
    repartition,
    variation,
)
from tests.test_reconciliation_api import account, company, operation

PERIODE = {"from": "2026-09-01", "to": "2026-09-30"}


def lire(client, headers, db, **params):
    params = {"company_id": str(company(db).id), **PERIODE, **params}
    return client.get("/api/dashboard", params=params, headers=headers)


@pytest.fixture
def comptable(client, reference):
    from tests.helpers import bearer, login, make_auth_user

    make_auth_user(reference, "COMPTABLE", email="comptable@example.com")
    return bearer(login(client, "comptable@example.com"))


# --- Règles pures ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("actuel", "precedent", "attendu"),
    [
        ("110", "100", "10.0"),
        ("90", "100", "-10.0"),
        ("-50", "-100", "50.0"),
        ("10", "0", None),
        ("10", None, None),
    ],
)
def test_variation(actuel, precedent, attendu):
    resultat = variation(Decimal(actuel), Decimal(precedent) if precedent is not None else None)

    assert resultat == (Decimal(attendu) if attendu else None)


@pytest.mark.parametrize(
    ("libelle", "code"),
    [
        ("FRAIS DE TENUE DE COMPTE", "tenue"),
        ("COMMISSION TENUE DE COMPTE", "tenue"),
        ("FRAIS RECUPERES PAR LA BANQUE", "recuperes"),
        ("AGIOS BANCAIRES", "agios"),
        ("INTERETS DEBITEURS", "agios"),
        ("DROIT DE TIMBRE SUR VERSEMENT", "timbres"),
        ("COMMISSION VIR. RTGS EMIS", "commissions"),
        ("TAXE SUR VALEUR AJOUTEE", "commissions"),
        ("DROITS DE GARDE DES TITRES", "autres"),
    ],
)
def test_a_fee_is_classified_by_its_label(libelle, code):
    assert categorie_frais(libelle)[0] == code


def test_evolution_keeps_the_last_known_balance_and_sums_accounts():
    soldes = {
        1: ((date(2026, 9, 2), Decimal("100")), (date(2026, 9, 4), Decimal("150"))),
        2: ((date(2026, 9, 3), Decimal("-20")),),
    }

    points = evolution(soldes, date(2026, 9, 1), date(2026, 9, 4))

    assert points == [
        (date(2026, 9, 1), None),
        (date(2026, 9, 2), Decimal("100")),
        (date(2026, 9, 3), Decimal("80")),
        (date(2026, 9, 4), Decimal("130")),
    ]


def test_flows_cover_every_day_with_zero_when_nothing_moved():
    points = flux(
        {date(2026, 9, 2): (Decimal("100"), Decimal("40"))}, date(2026, 9, 1), date(2026, 9, 2)
    )

    assert points == [
        (date(2026, 9, 1), Decimal("0.00"), Decimal("0.00")),
        (date(2026, 9, 2), Decimal("100"), Decimal("40")),
    ]


def test_fees_are_grouped_by_category_without_empty_ones():
    assert repartition(
        [("AGIOS", Decimal("10")), ("INTERETS", Decimal("5")), ("COMMISSION", Decimal("2"))]
    ) == [
        ("agios", "Agios et intérêts", Decimal("15")),
        ("commissions", "Commissions et TVA", Decimal("2")),
    ]


def test_alerts_put_line_overruns_first_and_skip_small_fee_rises():
    liste = alertes(
        depassements=[("BP", Decimal("-1200.00"))],
        a_rapprocher=18,
        a_comptabiliser=1,
        a_exporter=0,
        hausse_frais=Decimal("5.0"),
    )

    assert [(a.niveau, a.message) for a in liste] == [
        ("danger", "Dépassement de ligne : BP (-1200.00 DH)"),
        ("warning", "18 opérations à rapprocher"),
        ("warning", "1 frais bancaire à comptabiliser"),
    ]


# --- API ------------------------------------------------------------------------------------------


def test_the_dashboard_sums_mad_accounts_only_and_compares_with_the_previous_period(
    client, comptable, db
):
    awb = account(db)
    awb.credit_autorise = Decimal("500.00")
    eur = account(db, bank_code="CIH")
    eur.devise = "EUR"
    # Compte MAD sans aucun solde : sa LIGNE n'entre pas dans le disponible
    sans_solde = account(db, bank_code="BMCI")
    sans_solde.credit_autorise = Decimal("300.00")
    db.flush()
    # Mois précédent : solde 1 000 en fin d'août
    operation(
        db, awb, montant="1000", jour=date(2026, 8, 20), libelle="VIR A", solde=Decimal("1000")
    )
    operation(db, awb, montant="500", jour=date(2026, 9, 5), libelle="VIR B", solde=Decimal("1500"))
    operation(
        db, awb, montant="-2200", jour=date(2026, 9, 10), libelle="CHEQUE 1", solde=Decimal("-700")
    )
    operation(
        db,
        awb,
        montant="-30",
        jour=date(2026, 9, 12),
        libelle="AGIOS BANCAIRES",
        solde=Decimal("-730"),
    )
    operation(
        db, eur, montant="999", jour=date(2026, 9, 6), libelle="VIR EUR", solde=Decimal("999")
    )

    response = lire(client, comptable, db)

    assert response.status_code == 200, response.text
    body = response.json()
    # Le compte EUR n'entre jamais dans un total en DH
    assert body["solde_total"] == {"valeur": "-730.00", "variation": "-173.0"}
    # LIGNE des seuls comptes MAD : disponible = -730 + 500
    assert (body["ligne_totale"], body["disponible"]) == ("500.00", "-230.00")
    assert body["flux"][9] == {
        "date": "2026-09-10",
        "encaissements": "0.00",
        "decaissements": "2200.00",
    }
    assert len(body["flux"]) == 30
    assert body["a_comptabiliser"] == 1
    assert body["encaissements"]["valeur"] == "500.00"
    assert body["decaissements"]["valeur"] == "2230.00"
    assert body["frais"] == [{"code": "agios", "libelle": "Agios et intérêts", "total": "30.00"}]
    assert (body["a_rapprocher"], body["total_operations"]) == (4, 4)
    assert body["evolution"][4] == {"date": "2026-09-05", "solde": "1500.00"}
    assert [(c["bank_code"], c["devise"], c["solde"], c["ligne"]) for c in body["comptes"]] == [
        ("AWB", "MAD", "-730.00", "500.00"),
        ("CIH", "EUR", "999.00", None),
        ("BMCI", "MAD", None, "300.00"),
    ]
    assert body["comptes"][0]["bank_id"] == awb.bank_id
    assert [c["disponible"] for c in body["comptes"]] == ["-230.00", None, None]
    assert body["dernieres_operations"][0]["libelle"] == "AGIOS BANCAIRES"
    messages = [alerte["message"] for alerte in body["alertes"]]
    assert "Dépassement de ligne : AWB (-230.00 DH)" in messages
    assert "1 frais bancaire à comptabiliser" in messages

    cloche = client.get(
        "/api/dashboard/alertes", params={"company_id": str(company(db).id)}, headers=comptable
    )
    assert cloche.status_code == 200


def test_the_dashboard_needs_a_login_and_a_valid_period(client, comptable, db):
    assert lire(client, {}, db).status_code == 401
    assert (
        lire(client, comptable, db, **{"from": "2026-09-30", "to": "2026-09-01"}).status_code == 409
    )
    assert (
        lire(client, comptable, db, **{"from": "2025-01-01", "to": "2026-09-30"}).status_code == 409
    )


def test_a_company_without_data_gets_an_empty_dashboard(client, comptable, db):
    assert db.scalar(select(Bank).filter_by(code="AWB")) is not None

    body = lire(client, comptable, db).json()

    assert body["solde_total"] == {"valeur": None, "variation": None}
    assert body["disponible"] is None
    assert (body["total_operations"], body["frais"], body["alertes"]) == (0, [], [])


def test_a_fee_rise_alert_is_written_the_french_way():
    [alerte] = alertes(
        depassements=[],
        a_rapprocher=0,
        a_comptabiliser=0,
        a_exporter=0,
        hausse_frais=Decimal("12.5"),
    )

    assert alerte.message == "Frais bancaires en hausse (+12,5 %)"


# --- Onglets Suivi / Indicateurs et filtre banque (19/10/2026) ------------------------------------


def test_the_bank_filter_keeps_only_that_bank(client, comptable, db):
    awb = account(db)
    bmci = account(db, bank_code="BMCI")
    operation(
        db, awb, montant="1000", jour=date(2026, 9, 5), libelle="VIR A", solde=Decimal("1000")
    )
    operation(db, bmci, montant="200", jour=date(2026, 9, 6), libelle="VIR B", solde=Decimal("200"))
    operation(db, bmci, montant="-15", jour=date(2026, 9, 7), libelle="AGIOS BANCAIRES")

    tous = lire(client, comptable, db).json()
    seul = lire(client, comptable, db, bank_id=str(bmci.bank_id)).json()

    assert tous["solde_total"]["valeur"] == "1200.00"
    assert [b["code"] for b in tous["banques"]] == ["AWB", "BMCI"]
    assert seul["bank_id"] == bmci.bank_id
    assert [b["code"] for b in seul["banques_societe"]] == ["AWB", "BMCI"]
    assert seul["solde_total"]["valeur"] == "200.00"
    assert seul["encaissements"]["valeur"] == "200.00"
    assert [c["bank_code"] for c in seul["comptes"]] == ["BMCI"]
    assert [(b["code"], b["total"], b["frais"]) for b in seul["banques"]] == [("BMCI", 2, "15.00")]
    assert seul["taches"]["a_comptabiliser"] == 1


def test_the_tasks_count_strong_and_weak_proposals(client, comptable, db):
    from tests.test_reconciliation_api import ecriture, run

    compte = account(db)
    operation(db, compte, jour=date(2026, 9, 24))
    ecriture(db, compte, jour=date(2026, 9, 24))
    operation(db, compte, montant="700", jour=date(2026, 9, 10), libelle="VIR XYZ")
    ecriture(db, compte, montant="-700", jour=date(2026, 9, 14), libelle="Divers", numero_piece="Z")
    assert run(client, comptable, db).status_code == 200

    taches = lire(client, comptable, db).json()["taches"]

    assert (taches["propositions_fortes"], taches["propositions_a_verifier"]) == (1, 1)
    assert (taches["operations_ambigues"], taches["ecritures_ambigues"]) == (0, 0)
