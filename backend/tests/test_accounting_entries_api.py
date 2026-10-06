"""Lecture des écritures comptables importées de Sage / SI (P10)."""

from datetime import date
from decimal import Decimal
from itertools import count

import pytest
from sqlalchemy import select

from app.models import AccountingEntry, Bank, BankAccount, Company, ImportBatch, User
from tests.helpers import bearer, build_account, login, make_auth_user, save

URL = "/api/accounting/entries"
_seq = count(1)


@pytest.fixture
def direction(client, reference) -> dict[str, str]:
    make_auth_user(reference, "DIRECTION", email="direction@example.com")
    return bearer(login(client, "direction@example.com"))


def company(db, code: str = "SIMTIS") -> Company:
    return db.scalar(select(Company).filter_by(code=code))


def account(db, bank_code: str = "AWB", company_code: str = "SIMTIS") -> BankAccount:
    bank = db.scalar(select(Bank).filter_by(code=bank_code))
    numero = f"RIB-ENT-{next(_seq):06d}"
    return save(db, build_account(company(db, company_code), bank, numero=numero))


def entry(
    db, compte: BankAccount, jour: date, libelle="VIR", debit="0", credit="10", **over
) -> AccountingEntry:
    debit, credit = Decimal(debit), Decimal(credit)
    return save(
        db,
        AccountingEntry(
            company_id=compte.company_id,
            bank_account_id=compte.id,
            journal="BQ1",
            compte="5141",
            date_ecriture=jour,
            libelle=libelle,
            debit=debit,
            credit=credit,
            montant=credit - debit,
            hash_ligne=f"h{next(_seq)}",
            **over,
        ),
    )


def batch(db, nom: str = "sage.xlsx", **over) -> ImportBatch:
    return save(
        db,
        ImportBatch(
            type="Comptabilité",
            company_id=company(db).id,
            fichier_nom=nom,
            fichier_hash=f"{next(_seq):064d}",
            statut="Confirmé",
            **over,
        ),
    )


def get(client, headers, db, code: str = "SIMTIS", **params):
    params = {"company_id": str(company(db, code).id), **params}
    return client.get(URL, params=params, headers=headers)


def test_entries_are_listed_newest_first_with_totals(client, direction, db):
    awb = account(db)
    entry(db, awb, date(2025, 9, 1), credit="10")
    entry(db, awb, date(2025, 9, 3), debit="4", credit="0")

    response = get(client, direction, db)

    assert response.status_code == 200
    body = response.json()
    assert (body["total"], body["page"], body["taille"]) == (2, 1, 50)
    assert [item["date_ecriture"] for item in body["ecritures"]] == ["2025-09-03", "2025-09-01"]
    assert (body["total_debit"], body["total_credit"]) == ("4.00", "10.00")
    assert body["ecritures"][0]["bank_code"] == "AWB"
    assert body["ecritures"][0]["statut"] == "Non rapprochée"


def test_filters_by_account_dates_and_status(client, direction, db):
    awb, bp = account(db, "AWB"), account(db, "BP")
    entry(db, awb, date(2025, 9, 1))
    entry(db, bp, date(2025, 9, 2))
    entry(db, bp, date(2025, 9, 20), statut="Rapprochée")

    by_account = get(client, direction, db, bank_account_id=str(bp.id)).json()
    by_dates = get(client, direction, db, **{"from": "2025-09-02", "to": "2025-09-10"}).json()
    by_status = get(client, direction, db, statut="Rapprochée").json()

    assert by_account["total"] == 2
    assert by_dates["total"] == 1
    assert by_status["total"] == 1


def test_search_looks_in_label_piece_reference_and_third_party(client, direction, db):
    awb = account(db)
    entry(db, awb, date(2025, 9, 1), libelle="REG CLIENT ATLAS")
    entry(db, awb, date(2025, 9, 2), numero_piece="P-778")
    entry(db, awb, date(2025, 9, 3), tiers="Atlas Textile")
    entry(db, awb, date(2025, 9, 4), reference="CHQ 991")

    assert get(client, direction, db, q="atlas").json()["total"] == 2
    assert get(client, direction, db, q="p-778").json()["total"] == 1
    assert get(client, direction, db, q="991").json()["total"] == 1


def test_search_treats_like_wildcards_as_text(client, direction, db):
    awb = account(db)
    entry(db, awb, date(2025, 9, 1), libelle="REMISE 100%")
    entry(db, awb, date(2025, 9, 2), libelle="AUTRE")

    assert get(client, direction, db, q="%").json()["total"] == 1
    assert get(client, direction, db, q="_").json()["total"] == 0


def test_pagination_by_fifty_with_totals_over_the_whole_filter(client, direction, db):
    awb = account(db)
    for day in range(1, 31):
        entry(db, awb, date(2025, 8, day))
        entry(db, awb, date(2025, 9, day))

    page2 = get(client, direction, db, page="2").json()

    assert (page2["total"], page2["page"], len(page2["ecritures"])) == (60, 2, 10)
    assert page2["ecritures"][0]["date_ecriture"] == "2025-08-10"
    assert page2["total_credit"] == "600.00"


def test_page_beyond_the_last_is_empty(client, direction, db):
    entry(db, account(db), date(2025, 9, 1))

    body = get(client, direction, db, page="9").json()

    assert (body["total"], body["ecritures"]) == (1, [])


def test_inverted_period_is_refused(client, direction, db):
    response = get(client, direction, db, **{"from": "2025-09-10", "to": "2025-09-01"})

    assert response.status_code == 409


def test_other_company_entries_are_never_listed(client, direction, db):
    entry(db, account(db, "AWB", "SOCX"), date(2025, 9, 1))

    assert get(client, direction, db).json()["total"] == 0


def test_entry_detail_names_its_import(client, direction, db):
    author = db.scalar(select(User).filter_by(email="direction@example.com"))
    item = entry(db, account(db), date(2025, 9, 1), import_batch_id=batch(db, user_id=author.id).id)

    response = client.get(f"{URL}/{item.id}", headers=direction)

    assert response.status_code == 200
    body = response.json()
    assert (body["fichier_nom"], body["importe_par"], body["libelle"]) == (
        "sage.xlsx",
        author.nom,
        "VIR",
    )
    assert body["importe_le"] is not None


def test_imports_journal(client, direction, db):
    imported = batch(db, nb_lignes=2)
    awb = account(db)
    entry(db, awb, date(2025, 9, 1), import_batch_id=imported.id, credit="10")
    entry(db, awb, date(2025, 9, 4), import_batch_id=imported.id, debit="3", credit="0")

    response = client.get(
        "/api/accounting/imports", params={"company_id": str(company(db).id)}, headers=direction
    )

    [row] = response.json()
    assert row | {"id": 0, "importe_le": None} == {
        "id": 0,
        "importe_le": None,
        "importe_par": None,
        "fichier_nom": "sage.xlsx",
        "periode_debut": "2025-09-01",
        "periode_fin": "2025-09-04",
        "nb_ecritures": 2,
        "total_debit": "3.00",
        "total_credit": "10.00",
    }


def test_unknown_entry_gives_404(client, direction):
    response = client.get(f"{URL}/999999", headers=direction)

    assert response.status_code == 404
    assert response.json() == {"detail": "Écriture introuvable."}


def test_unknown_company_gives_404(client, direction):
    assert client.get(URL, params={"company_id": "999999"}, headers=direction).status_code == 404


def test_requires_a_token(client, reference):
    assert client.get(URL, params={"company_id": "1"}).status_code == 401


def test_requires_a_reading_permission(client, reference, db):
    make_auth_user(reference, email="sans-role@example.com")
    headers = bearer(login(client, "sans-role@example.com"))

    assert get(client, headers, db).status_code == 403
