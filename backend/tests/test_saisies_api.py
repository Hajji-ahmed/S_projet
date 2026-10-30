"""Tableaux Devises et Prévisions saisis à la main (page Position bancaire)."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, Bank, Company, SaisieDevise, SaisiePrevisionJour
from app.services.position_service import business_today
from tests.helpers import bearer, login, make_auth_user

DAY = date(2026, 9, 30)
DEVISES = "/api/position/devises"
PREVISIONS = "/api/position/previsions"


@pytest.fixture
def tresorerie(client, reference) -> dict[str, str]:
    make_auth_user(reference, "TRESORERIE", email="tresorerie@example.com", nom="Salma")
    return bearer(login(client, "tresorerie@example.com"))


@pytest.fixture
def direction(client, reference) -> dict[str, str]:
    make_auth_user(reference, "DIRECTION", email="direction@example.com")
    return bearer(login(client, "direction@example.com"))


@pytest.fixture
def comptable(client, reference) -> dict[str, str]:
    make_auth_user(reference, "COMPTABLE", email="comptable@example.com")
    return bearer(login(client, "comptable@example.com"))


def company_id(db, code: str = "SIMTIS") -> int:
    return db.scalar(select(Company.id).filter_by(code=code))


def bank_id(db, code: str) -> int:
    return db.scalar(select(Bank.id).filter_by(code=code))


def params(db, code: str = "SIMTIS", jour: date = DAY) -> dict[str, str]:
    return {"company_id": str(company_id(db, code)), "date": jour.isoformat()}


def audit(db, action: str) -> list[AuditLog]:
    return list(db.scalars(select(AuditLog).filter_by(action=action).order_by(AuditLog.id)))


def line(body: dict, name) -> dict:
    return next(item for item in body["lignes"] if item["ligne"] == name)


# --- Devises ---------------------------------------------------------------------------------------


def test_empty_devises_grid_has_the_three_lines(client, direction, db):
    response = client.get(DEVISES, params=params(db), headers=direction)

    assert response.status_code == 200
    assert response.json() == {
        "company_id": company_id(db),
        "jour": DAY.isoformat(),
        "lignes": [
            {"ligne": ligne, "banques": [], "total": None, "depassement": None}
            for ligne in ("EUR", "USD", "Exp DH convertible")
        ],
    }


def test_devises_grid_is_saved_as_entered_without_any_calculation(client, tresorerie, db):
    awb, bp = bank_id(db, "AWB"), bank_id(db, "BP")
    body = {
        "lignes": [
            {
                "ligne": "EUR",
                "banques": [
                    {"bank_id": awb, "montant": "100.5"},
                    {"bank_id": bp, "montant": "-200"},
                ],
                "depassement": "7",
            },
            {"ligne": "Exp DH convertible", "banques": [], "total": "999"},
        ]
    }

    saved = client.put(DEVISES, params=params(db), json=body, headers=tresorerie)
    again = client.get(DEVISES, params=params(db), headers=tresorerie).json()

    assert saved.status_code == 200
    assert saved.json() == again
    eur = line(again, "EUR")
    assert sorted((c["bank_id"], c["montant"]) for c in eur["banques"]) == sorted(
        [(awb, "100.50"), (bp, "-200.00")]
    )
    assert eur["total"] is None  # jamais calculé : vide tant qu'il n'est pas saisi
    assert eur["depassement"] == "7.00"
    assert line(again, "USD") == {"ligne": "USD", "banques": [], "total": None, "depassement": None}
    assert line(again, "Exp DH convertible")["total"] == "999.00"


def test_saving_again_replaces_the_grid_and_audits_only_the_changes(client, tresorerie, db):
    awb, bp = bank_id(db, "AWB"), bank_id(db, "BP")
    first = {
        "lignes": [
            {
                "ligne": "EUR",
                "banques": [{"bank_id": awb, "montant": "100"}, {"bank_id": bp, "montant": "5"}],
                "total": "105",
            }
        ]
    }
    client.put(DEVISES, params=params(db), json=first, headers=tresorerie)
    second = {
        "lignes": [
            {"ligne": "EUR", "banques": [{"bank_id": awb, "montant": "150"}], "total": "105"}
        ]
    }

    response = client.put(DEVISES, params=params(db), json=second, headers=tresorerie)

    eur = line(response.json(), "EUR")
    assert eur["banques"] == [{"bank_id": awb, "montant": "150.00"}]  # BP vidé
    first_entry, second_entry = audit(db, "saisie_devises")
    assert first_entry.ancienne_valeur == {
        "jour": DAY.isoformat(),
        "EUR · AWB": None,
        "EUR · BP": None,
        "EUR · TOTAL": None,
    }
    assert second_entry.ancienne_valeur == {
        "jour": DAY.isoformat(),
        "EUR · AWB": "100.00",
        "EUR · BP": "5.00",
    }
    assert second_entry.nouvelle_valeur == {
        "jour": DAY.isoformat(),
        "EUR · AWB": "150.00",
        "EUR · BP": None,
    }


def test_same_devises_grid_again_writes_no_audit(client, tresorerie, db):
    body = {"lignes": [{"ligne": "USD", "total": "1"}]}
    client.put(DEVISES, params=params(db), json=body, headers=tresorerie)

    client.put(DEVISES, params=params(db), json=body, headers=tresorerie)

    assert len(audit(db, "saisie_devises")) == 1


def test_devises_grids_are_separate_per_company_and_per_date(client, tresorerie, db):
    body = {"lignes": [{"ligne": "USD", "total": "1"}]}
    client.put(DEVISES, params=params(db), json=body, headers=tresorerie)

    other_company = client.get(DEVISES, params=params(db, "SOCX"), headers=tresorerie).json()
    other_day = client.get(
        DEVISES, params=params(db, jour=DAY - timedelta(days=1)), headers=tresorerie
    ).json()

    assert line(other_company, "USD")["total"] is None
    assert line(other_day, "USD")["total"] is None


def test_devises_grid_defaults_to_today(client, direction, db):
    response = client.get(DEVISES, params={"company_id": company_id(db)}, headers=direction)

    assert response.json()["jour"] == business_today().isoformat()


def test_inactive_bank_cannot_be_entered_but_its_values_are_kept(client, tresorerie, db):
    bmci = db.scalar(select(Bank).filter_by(code="BMCI"))
    body = {"lignes": [{"ligne": "EUR", "banques": [{"bank_id": bmci.id, "montant": "1"}]}]}
    client.put(DEVISES, params=params(db), json=body, headers=tresorerie)
    bmci.actif = False
    db.flush()

    refused = client.put(DEVISES, params=params(db), json=body, headers=tresorerie)
    emptied = client.put(DEVISES, params=params(db), json={"lignes": []}, headers=tresorerie)

    assert refused.status_code == 409
    assert refused.json() == {"detail": f"Banque inconnue ou inactive : {bmci.id}."}
    assert line(emptied.json(), "EUR")["banques"] == [{"bank_id": bmci.id, "montant": "1.00"}]


def test_unknown_bank_gives_409(client, tresorerie, db):
    body = {"lignes": [{"ligne": "EUR", "banques": [{"bank_id": 999999, "montant": "1"}]}]}

    response = client.put(DEVISES, params=params(db), json=body, headers=tresorerie)

    assert response.status_code == 409
    assert db.scalar(select(SaisieDevise)) is None


def test_unknown_company_gives_404(client, tresorerie, db):
    response = client.get(
        DEVISES, params={"company_id": "999999", "date": DAY.isoformat()}, headers=tresorerie
    )

    assert response.status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"lignes": [{"ligne": "GBP"}]},
        {"lignes": [{"ligne": "EUR"}, {"ligne": "EUR"}]},
        {"lignes": [{"ligne": "EUR", "total": "1.234"}]},
        {"lignes": [{"ligne": "EUR", "inconnu": "x"}]},
        {"lignes": [{"ligne": "EUR", "banques": [{"bank_id": 1, "montant": "1"}] * 2}]},
    ],
)
def test_invalid_devises_grid_gives_422(client, tresorerie, db, body):
    assert client.put(DEVISES, params=params(db), json=body, headers=tresorerie).status_code == 422


def test_saving_needs_a_date(client, tresorerie, db):
    response = client.put(
        DEVISES, params={"company_id": company_id(db)}, json={"lignes": []}, headers=tresorerie
    )

    assert response.status_code == 422


def test_direction_reads_but_cannot_enter_devises(client, direction, db):
    body = {"lignes": [{"ligne": "USD", "total": "1"}]}

    assert client.get(DEVISES, params=params(db), headers=direction).status_code == 200
    assert client.put(DEVISES, params=params(db), json=body, headers=direction).status_code == 403
    assert db.scalar(select(SaisieDevise)) is None


def test_comptable_cannot_enter_devises(client, comptable, db):
    body = {"lignes": [{"ligne": "USD", "total": "1"}]}

    assert client.put(DEVISES, params=params(db), json=body, headers=comptable).status_code == 403


# --- Prévisions ------------------------------------------------------------------------------------

LATER = DAY + timedelta(days=5)


def put_previsions(client, db, headers, lignes, jour: date = DAY):
    return client.put(
        PREVISIONS, params=params(db, jour=jour), json={"lignes": lignes}, headers=headers
    )


def keys(body: dict) -> list[tuple[str, int, str | None]]:
    return [(item["jour"], item["ligne"], item["libelle"]) for item in body["lignes"]]


def test_empty_previsions_table_has_no_line(client, direction, db):
    """Décision du 30/10/2026 : plus de bloc fixe de 14 lignes, la Trésorerie ajoute ses lignes."""
    body = client.get(PREVISIONS, params=params(db), headers=direction).json()

    assert body["lignes"] == []
    assert "encaissement" not in body


def test_previsions_round_trip_with_a_date_per_line(client, tresorerie, db):
    cih = bank_id(db, "CIH")
    lignes = [
        {
            "jour": DAY.isoformat(),
            "libelle": "  Client A  ",
            "banques": [{"bank_id": cih, "montant": "1000"}],
            "encaissement": "250000",
        },
        {"jour": LATER.isoformat(), "escompte": "5"},  # seulement un montant sans banque
        {
            "jour": DAY.isoformat(),
            "libelle": "   ",
            "banques": [{"bank_id": cih, "montant": "-50.25"}],
            "douane": "-12000.5",
        },
    ]

    saved = put_previsions(client, db, tresorerie, lignes).json()
    again = client.get(PREVISIONS, params=params(db), headers=tresorerie).json()

    assert saved == again
    # Triées par date ; rangs donnés dans l'ordre d'envoi pour chaque date
    assert keys(again) == [
        (DAY.isoformat(), 1, "Client A"),
        (DAY.isoformat(), 2, None),  # un libellé blanc est une cellule vide
        (LATER.isoformat(), 1, None),
    ]
    assert again["lignes"][0] == {
        "jour": DAY.isoformat(),
        "ligne": 1,
        "libelle": "Client A",
        "banques": [{"bank_id": cih, "montant": "1000.00"}],
        "encaissement": "250000.00",
        "escompte": None,
        "douane": None,
    }
    assert again["lignes"][1]["douane"] == "-12000.50"
    assert again["lignes"][2]["escompte"] == "5.00"


def test_previsions_shows_lines_from_the_chosen_date_onwards(client, tresorerie, db):
    put_previsions(
        client,
        db,
        tresorerie,
        [
            {"jour": DAY.isoformat(), "libelle": "Aujourd'hui"},
            {"jour": LATER.isoformat(), "libelle": "Plus tard"},
        ],
    )

    body = client.get(
        PREVISIONS, params=params(db, jour=DAY + timedelta(days=1)), headers=tresorerie
    )

    assert keys(body.json()) == [(LATER.isoformat(), 1, "Plus tard")]


def test_saving_from_a_later_date_keeps_older_lines(client, tresorerie, db):
    put_previsions(
        client,
        db,
        tresorerie,
        [
            {"jour": DAY.isoformat(), "libelle": "Ancienne"},
            {"jour": LATER.isoformat(), "libelle": "Plus tard"},
        ],
    )

    put_previsions(client, db, tresorerie, [], jour=DAY + timedelta(days=1))

    body = client.get(PREVISIONS, params=params(db), headers=tresorerie).json()
    assert keys(body) == [(DAY.isoformat(), 1, "Ancienne")]


def test_deleted_line_is_removed_renumbered_and_audited(client, tresorerie, db):
    cih = bank_id(db, "CIH")
    put_previsions(
        client,
        db,
        tresorerie,
        [
            {"jour": DAY.isoformat(), "libelle": "Client A", "escompte": "10"},
            {
                "jour": DAY.isoformat(),
                "libelle": "Client B",
                "banques": [{"bank_id": cih, "montant": "1"}],
            },
        ],
    )

    # La ligne « Client A » est supprimée : « Client B » devient la ligne 1
    response = put_previsions(
        client,
        db,
        tresorerie,
        [
            {
                "jour": DAY.isoformat(),
                "libelle": "Client B",
                "banques": [{"bank_id": cih, "montant": "1"}],
            }
        ],
    )

    assert response.json()["lignes"] == [
        {
            "jour": DAY.isoformat(),
            "ligne": 1,
            "libelle": "Client B",
            "banques": [{"bank_id": cih, "montant": "1.00"}],
            "encaissement": None,
            "escompte": None,
            "douane": None,
        }
    ]
    assert db.scalar(select(SaisiePrevisionJour)) is None  # trois cellules vides : ligne supprimée
    entry = audit(db, "saisie_previsions")[-1]
    assert entry.ancienne_valeur == {
        "a_partir_du": DAY.isoformat(),
        "30/09/2026 · Ligne 1 · libellé": "Client A",
        "30/09/2026 · Ligne 1 · CIH": None,
        "30/09/2026 · Ligne 1 · Escompte": "10.00",
        "30/09/2026 · Ligne 2 · libellé": "Client B",
        "30/09/2026 · Ligne 2 · CIH": "1.00",
    }
    assert entry.nouvelle_valeur == {
        "a_partir_du": DAY.isoformat(),
        "30/09/2026 · Ligne 1 · libellé": "Client B",
        "30/09/2026 · Ligne 1 · CIH": "1.00",
        "30/09/2026 · Ligne 1 · Escompte": None,
        "30/09/2026 · Ligne 2 · libellé": None,
        "30/09/2026 · Ligne 2 · CIH": None,
    }


def test_same_previsions_again_writes_no_audit(client, tresorerie, db):
    lignes = [{"jour": DAY.isoformat(), "libelle": "Client A", "encaissement": "1"}]
    put_previsions(client, db, tresorerie, lignes)

    put_previsions(client, db, tresorerie, lignes)

    assert len(audit(db, "saisie_previsions")) == 1


def test_empty_added_line_is_not_saved(client, tresorerie, db):
    body = put_previsions(
        client,
        db,
        tresorerie,
        [{"jour": DAY.isoformat()}, {"jour": LATER.isoformat(), "libelle": "A"}],
    ).json()

    assert keys(body) == [(LATER.isoformat(), 1, "A")]


def test_line_before_the_chosen_date_gives_409(client, tresorerie, db):
    response = put_previsions(
        client, db, tresorerie, [{"jour": (DAY - timedelta(days=1)).isoformat(), "libelle": "A"}]
    )

    assert response.status_code == 409
    assert "antérieure" in response.json()["detail"]


def test_mistyped_year_gives_409(client, tresorerie, db):
    response = put_previsions(
        client, db, tresorerie, [{"jour": "0026-10-01", "libelle": "A"}], jour=date(1, 1, 1)
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Date invalide : 01/10/0026."


def test_at_most_99_lines_per_date(client, tresorerie, db):
    lignes = [{"jour": DAY.isoformat(), "libelle": f"L{n}"} for n in range(100)]

    response = put_previsions(client, db, tresorerie, lignes)

    assert response.status_code == 409
    assert "99 lignes" in response.json()["detail"]


def test_future_previsions_can_be_entered(client, tresorerie, db):
    future = business_today() + timedelta(days=30)

    response = put_previsions(
        client, db, tresorerie, [{"jour": future.isoformat(), "encaissement": "1"}], jour=future
    )

    assert response.status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {"lignes": [{"libelle": "sans date"}]},
        {"lignes": [{"jour": "2026-13-01"}]},
        {"lignes": [{"jour": "2026-09-30", "ligne": 1}]},  # le rang est donné par le serveur
        {"lignes": [{"jour": "2026-09-30", "libelle": "x" * 81}]},
        {"lignes": [{"jour": "2026-09-30", "encaissement": "abc"}]},
        {"lignes": [{"jour": "2026-09-30", "douane": "1.234"}]},
        {"lignes": [], "encaissement": "1"},
        {"lignes": [], "inconnu": "x"},
    ],
)
def test_invalid_previsions_gives_422(client, tresorerie, db, body):
    assert (
        client.put(PREVISIONS, params=params(db), json=body, headers=tresorerie).status_code == 422
    )


def test_direction_and_comptable_cannot_enter_previsions(client, direction, comptable, db):
    body = {"lignes": [{"jour": DAY.isoformat(), "encaissement": "1"}]}

    assert client.get(PREVISIONS, params=params(db), headers=direction).status_code == 200
    for headers in (direction, comptable):
        assert (
            client.put(PREVISIONS, params=params(db), json=body, headers=headers).status_code == 403
        )
