"""Import d'un export Sage / SI (P10) : analyse et confirmation."""

import json
from datetime import date
from decimal import Decimal
from io import BytesIO
from itertools import count

import pytest
from openpyxl import Workbook
from sqlalchemy import func, select

from app.models import (
    AccountingEntry,
    AuditLog,
    Bank,
    BankAccount,
    ColumnMapping,
    Company,
    ImportBatch,
)
from app.repositories import accounting_repository
from tests.helpers import bearer, big_xlsx, build_account, login, make_auth_user, save, xls

ANALYSE = "/api/accounting/import/analyse"
CONFIRM = "/api/accounting/import/confirm"
HEADER = [
    "Date",
    "Journal",
    "Compte",
    "N° pièce",
    "Libellé",
    "Débit",
    "Crédit",
    "Échéance",
    "Tiers",
]
_numeros = count(1)


def xlsx(rows: list[list]) -> bytes:
    workbook = Workbook()
    for row in rows:
        workbook.active.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


EXPORT = [
    ["Grand livre — export Sage"],
    HEADER,
    [date(2025, 9, 2), "BQ1", "5141", "P001", "REG CLIENT ATLAS", 38500, None, None, "ATLAS"],
    [date(2025, 9, 2), "BQ1", "3421", "P001", "REG CLIENT ATLAS", None, 38500, None, "ATLAS"],
    [
        date(2025, 9, 3),
        "BQ2",
        "5141",
        "P002",
        "VIR FOURNISSEUR TEXTILE",
        None,
        12800,
        date(2025, 9, 30),
        None,
    ],
    [date(2025, 9, 3), "ACH", "4411", "F77", "FACTURE ACHAT", None, 500, None, "TEXTILE"],
]


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


def account(
    db, bank_code: str, journal: str | None, company_code: str = "SIMTIS", **over
) -> BankAccount:
    over.setdefault("numero", f"RIB-CPT-{next(_numeros):06d}")
    over.setdefault("compte_comptable", "5141")
    bank = db.scalar(select(Bank).filter_by(code=bank_code))
    return save(db, build_account(company(db, company_code), bank, journal_sage=journal, **over))


@pytest.fixture
def journals(db, reference) -> tuple[BankAccount, BankAccount]:
    return account(db, "AWB", "BQ1"), account(db, "BP", "BQ2")


def post(client, url, headers, db, content, *, code="SIMTIS", nom="export.xlsx", **form):
    data = {"company_id": str(company(db, code).id), **form}
    if isinstance(data.get("mapping"), dict):
        data["mapping"] = json.dumps(data["mapping"])
    files = {"fichier": (nom, content, "application/octet-stream")}
    return client.post(url, data=data, files=files, headers=headers)


def analyse(client, headers, db, content, **form):
    return post(client, ANALYSE, headers, db, content, **form)


# --- Analyse ---------------------------------------------------------------------------------------


def test_bank_lines_are_kept_and_attached_by_their_journal(client, comptable, db, journals):
    awb, bp = journals

    response = analyse(client, comptable, db, xlsx(EXPORT))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ligne_entete"] == 2
    assert body["mapping_source"] == "Détection"
    assert body["erreurs_mapping"] == []
    lines = body["lignes"]
    assert [
        (line["journal"], line["compte"], line["bank_account_id"], line["statut"]) for line in lines
    ] == [
        ("BQ1", "5141", awb.id, "Valide"),
        ("BQ2", "5141", bp.id, "Valide"),
    ]
    assert lines[0] | {"hash_ligne": None} == {
        "numero": 3,
        "statut": "Valide",
        "motifs": [],
        "date_ecriture": "2025-09-02",
        "journal": "BQ1",
        "compte": "5141",
        "libelle": "REG CLIENT ATLAS",
        "reference": None,
        "debit": "38500.00",
        "credit": "0.00",
        "montant": "-38500.00",
        "numero_piece": "P001",
        "echeance": None,
        "tiers": "ATLAS",
        "bank_account_id": awb.id,
        "bank_code": "AWB",
        "hash_ligne": None,
        "doublon_de": None,
    }
    assert lines[1]["echeance"] == "2025-09-30"
    resume = body["resume"]
    assert (resume["nb_valides"], resume["nb_ignorees"], resume["nb_erreurs"]) == (2, 2, 0)
    assert (resume["total_debit"], resume["total_credit"]) == ("38500.00", "12800.00")
    assert (resume["periode_debut"], resume["periode_fin"]) == ("2025-09-02", "2025-09-03")
    assert [item["bank_code"] for item in resume["par_compte"]] == ["AWB", "BP"]


def test_journal_is_matched_whatever_its_case(client, comptable, db, journals):
    rows = [HEADER, [date(2025, 9, 2), " bq1 ", "5141", "P1", "VIR", 10, None, None, None]]

    [line] = analyse(client, comptable, db, xlsx(rows)).json()["lignes"]

    assert (line["journal"], line["bank_code"]) == ("BQ1", "AWB")


def test_numeric_account_cell_is_read_as_text(client, comptable, db, journals):
    rows = [HEADER, [date(2025, 9, 2), "BQ1", 514100, "P1", "VIR", 10, None, None, None]]

    [line] = analyse(client, comptable, db, xlsx(rows)).json()["lignes"]

    assert (line["compte"], line["statut"]) == ("514100", "Valide")


def test_bank_account_without_accounting_code_keeps_every_line_of_its_journal(
    client, comptable, db, reference
):
    account(db, "AWB", "BQ1", compte_comptable=None)
    rows = [HEADER, [date(2025, 9, 2), "BQ1", "3421", "P1", "VIR", 10, None, None, None]]

    assert len(analyse(client, comptable, db, xlsx(rows)).json()["lignes"]) == 1


def test_inactive_account_journal_is_ignored(client, comptable, db, reference):
    account(db, "AWB", "BQ1", actif=False)
    active = account(db, "CIH", "BQ1")

    [line] = analyse(client, comptable, db, xlsx(EXPORT[:3])).json()["lignes"]

    assert line["bank_account_id"] == active.id


def test_signed_amount_column(client, comptable, db, journals):
    rows = [
        ["Date", "Journal", "Compte", "Libellé", "Montant"],
        [date(2025, 9, 2), "BQ1", "5141", "VIR RECU", 100],
        [date(2025, 9, 3), "BQ1", "5141", "VIR EMIS", -40],
    ]

    lines = analyse(client, comptable, db, xlsx(rows)).json()["lignes"]

    assert [(line["debit"], line["credit"]) for line in lines] == [
        ("0.00", "100.00"),
        ("40.00", "0.00"),
    ]


@pytest.mark.parametrize(
    ("cells", "motif"),
    [
        ({1: None}, "Date manquante."),
        ({1: "31/02/2025"}, "Date : Date illisible"),
        ({5: None}, "Libellé manquant."),
        ({6: "dix"}, "Débit : Montant illisible"),
        ({6: None}, "Montant manquant ou nul."),
        ({7: 5}, "Débit et crédit renseignés sur la même ligne."),
        # Un montant négatif (extourne dans Sage) n'est jamais remis en positif sans le dire
        ({6: -10}, "Débit négatif."),
        ({6: None, 7: -10}, "Crédit négatif."),
        ({8: "plus tard"}, "Échéance : Date illisible"),
        ({9: "T" * 121}, "Tiers : 120 caractères au plus."),
    ],
)
def test_invalid_bank_lines_are_errors(client, comptable, db, journals, cells, motif):
    row = [date(2025, 9, 2), "BQ1", "5141", "P1", "VIR", 10, None, None, None]
    for index, value in cells.items():
        row[index - 1] = value

    [line] = analyse(client, comptable, db, xlsx([HEADER, row])).json()["lignes"]

    assert line["statut"] == "Erreur"
    assert any(text.startswith(motif) for text in line["motifs"]), line["motifs"]


def test_future_date_is_an_error(client, comptable, db, journals):
    row = [date(2099, 1, 1), "BQ1", "5141", "P1", "VIR", 10, None, None, None]

    [line] = analyse(client, comptable, db, xlsx([HEADER, row])).json()["lignes"]

    assert "Date dans le futur." in line["motifs"]


def test_identical_lines_in_the_file_are_duplicates(client, comptable, db, journals):
    row = [date(2025, 9, 2), "BQ1", "5141", "P1", "FRAIS", 10, None, None, None]

    lines = analyse(client, comptable, db, xlsx([HEADER, row, row])).json()["lignes"]

    assert [(line["statut"], line["doublon_de"]) for line in lines] == [
        ("Valide", None),
        ("Doublon", 2),
    ]


def test_company_without_sage_journal_is_refused(client, comptable, db, reference):
    account(db, "AWB", None)

    response = analyse(client, comptable, db, xlsx(EXPORT))

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Renseignez le journal Sage de vos comptes bancaires (écran Comptes)."
    }


def test_journals_of_another_company_are_never_used(client, comptable, db, reference):
    account(db, "AWB", "BQ1", company_code="SOCX")
    account(db, "BP", "BQ9")

    body = analyse(client, comptable, db, xlsx(EXPORT)).json()

    assert body["lignes"] == []
    assert body["resume"]["nb_ignorees"] == 4


def test_unrecognised_columns_give_mapping_errors(client, comptable, db, journals):
    rows = [["A", "B", "C"], [date(2025, 9, 2), "BQ1", 10]]

    body = analyse(client, comptable, db, xlsx(rows)).json()

    assert "Colonne obligatoire non associée : Date." in body["erreurs_mapping"]
    assert body["lignes"] == []


def test_analysis_writes_nothing(client, comptable, db, journals):
    before = db.scalar(select(func.count()).select_from(AccountingEntry))

    analyse(client, comptable, db, xlsx(EXPORT))

    assert db.scalar(select(func.count()).select_from(AccountingEntry)) == before


def test_unknown_company_gives_404(client, comptable, db, journals):
    files = {"fichier": ("export.xlsx", xlsx(EXPORT), "application/octet-stream")}

    response = client.post(ANALYSE, data={"company_id": "999999"}, files=files, headers=comptable)

    assert response.status_code == 404


def test_direction_cannot_import(client, direction, db, journals):
    assert analyse(client, direction, db, xlsx(EXPORT)).status_code == 403


def test_requires_a_token(client, reference):
    assert client.post(ANALYSE).status_code == 401


# --- Confirmation ----------------------------------------------------------------------------------


def confirm(client, headers, db, content, **form):
    return post(client, CONFIRM, headers, db, content, **form)


def test_confirmed_export_saves_the_bank_lines(client, comptable, db, journals):
    awb, bp = journals

    response = confirm(client, comptable, db, xlsx(EXPORT))

    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["nb_importees"], body["nb_erreurs_ecartees"], body["nb_doublons_ecartes"]) == (
        2,
        0,
        0,
    )
    assert [item["bank_code"] for item in body["par_compte"]] == ["AWB", "BP"]
    entries = db.scalars(select(AccountingEntry).order_by(AccountingEntry.id)).all()
    assert [
        (e.bank_account_id, e.journal, e.debit, e.credit, e.montant, e.statut) for e in entries
    ] == [
        (
            awb.id,
            "BQ1",
            Decimal("38500.00"),
            Decimal("0.00"),
            Decimal("-38500.00"),
            "Non rapprochée",
        ),
        (bp.id, "BQ2", Decimal("0.00"), Decimal("12800.00"), Decimal("12800.00"), "Non rapprochée"),
    ]
    batch = db.get(ImportBatch, body["import_id"])
    assert (batch.type, batch.statut, batch.nb_lignes, batch.company_id) == (
        "Comptabilité",
        "Confirmé",
        2,
        company(db).id,
    )
    [entry] = db.scalars(select(AuditLog).filter_by(action="import_ecritures")).all()
    assert entry.nouvelle_valeur["fichier"] == "export.xlsx"
    assert entry.nouvelle_valeur["ecritures"] == 2
    assert entry.nouvelle_valeur["par_compte"] == {"AWB · BQ1": 1, "BP · BQ2": 1}


def test_two_accounts_of_the_same_bank_are_counted_apart(client, comptable, db, reference):
    account(db, "AWB", "BQ1")
    account(db, "AWB", "BQ3", devise="EUR")
    rows = [
        HEADER,
        [date(2025, 9, 2), "BQ1", "5141", "P1", "VIR MAD", 10, None, None, None],
        [date(2025, 9, 2), "BQ3", "5141", "P2", "VIR EUR", 20, None, None, None],
    ]

    body = confirm(client, comptable, db, xlsx(rows)).json()

    assert [(item["bank_code"], item["journal"], item["nb"]) for item in body["par_compte"]] == [
        ("AWB", "BQ1", 1),
        ("AWB", "BQ3", 1),
    ]
    [entry] = db.scalars(select(AuditLog).filter_by(action="import_ecritures")).all()
    assert entry.nouvelle_valeur["par_compte"] == {"AWB · BQ1": 1, "AWB · BQ3": 1}


def test_mapping_is_remembered_for_the_company(client, comptable, db, journals):
    rows = [["Dt", "Jnl", "Cpt", "Lib", "Mnt"], [date(2025, 9, 2), "BQ1", "5141", "VIR", 10]]
    mapping = {"date_ecriture": 0, "journal": 1, "compte": 2, "libelle": 3, "montant": 4}
    confirm(client, comptable, db, xlsx(rows), mapping=mapping)

    rows[1][3] = "AUTRE VIR"
    body = analyse(client, comptable, db, xlsx(rows), nom="export2.xlsx").json()

    assert body["mapping_source"] == "Modèle de la société"
    assert body["lignes"][0]["statut"] == "Valide"
    saved = db.scalar(select(ColumnMapping).filter_by(type="Comptabilité"))
    assert (saved.company_id, saved.bank_id) == (company(db).id, None)


def test_errors_block_the_confirmation_unless_discarded(client, comptable, db, journals):
    bad = [date(2025, 9, 4), "BQ1", "5141", "P9", None, 5, None, None, None]
    content = xlsx([*EXPORT, bad])

    refused = confirm(client, comptable, db, content)
    accepted = confirm(client, comptable, db, content, ecarter_erreurs="true")

    assert refused.status_code == 409
    assert refused.json() == {
        "detail": "1 ligne en erreur : corrigez l'export dans Sage, ou confirmez en l'écartant."
    }
    assert accepted.status_code == 201
    assert accepted.json()["nb_erreurs_ecartees"] == 1


def test_same_file_cannot_be_imported_twice(client, comptable, db, journals):
    # Un seul fichier : openpyxl date chaque classeur, deux fichiers construits ne sont pas identiques
    content = xlsx(EXPORT)
    confirm(client, comptable, db, content)

    again = confirm(client, comptable, db, content)

    assert again.status_code == 409
    assert again.json() == {"detail": "Ce fichier a déjà été importé pour cette société."}


def test_lines_already_imported_are_skipped_in_a_new_file(client, comptable, db, journals):
    confirm(client, comptable, db, xlsx(EXPORT))
    newer = [*EXPORT, [date(2025, 9, 5), "BQ1", "5141", "P003", "FRAIS", 50, None, None, None]]

    body = confirm(client, comptable, db, xlsx(newer)).json()

    assert (body["nb_importees"], body["nb_doublons_ecartes"]) == (1, 2)


def test_internal_duplicate_can_be_kept(client, comptable, db, journals):
    row = [date(2025, 9, 2), "BQ1", "5141", "P1", "FRAIS", 10, None, None, None]

    body = confirm(client, comptable, db, xlsx([HEADER, row, row]), garder_doublons="[3]").json()

    assert body["nb_importees"] == 2


def test_a_line_that_is_not_an_internal_duplicate_cannot_be_kept(client, comptable, db, journals):
    response = confirm(client, comptable, db, xlsx(EXPORT), garder_doublons="[3]")

    assert response.status_code == 409


def test_file_without_bank_line_is_refused(client, comptable, db, journals):
    response = confirm(client, comptable, db, xlsx(EXPORT[:2] + EXPORT[5:]))

    assert response.status_code == 409
    assert response.json() == {"detail": "Aucune écriture de banque à importer dans ce fichier."}


def test_direction_cannot_confirm(client, direction, db, journals):
    assert confirm(client, direction, db, xlsx(EXPORT)).status_code == 403


def test_xls_export_is_analysed_like_the_xlsx(client, comptable, db, journals):
    as_xlsx = analyse(client, comptable, db, xlsx(EXPORT)).json()
    response = analyse(client, comptable, db, xls(("Export", EXPORT)), nom="sage.xls")

    assert response.status_code == 200, response.text
    body = response.json()
    assert [
        (line["journal"], line["bank_account_id"], line["debit"], line["credit"])
        for line in body["lignes"]
    ] == [
        (line["journal"], line["bank_account_id"], line["debit"], line["credit"])
        for line in as_xlsx["lignes"]
    ]
    assert body["resume"]["nb_ignorees"] == as_xlsx["resume"]["nb_ignorees"]


def test_ignored_lines_come_back_with_their_reason(client, comptable, db, journals):
    body = analyse(client, comptable, db, xlsx(EXPORT)).json()

    assert [(line["numero"], line["raison"]) for line in body["lignes_ignorees"]] == [
        (4, "Compte 3421 : contrepartie, pas la ligne banque (5141…) du journal BQ1"),
        (6, "Journal « ACH » : pas le journal Sage d'un compte bancaire"),
    ]
    assert body["lignes_ignorees"][1]["cellules"][:5] == [
        "03/09/2025",
        "ACH",
        "4411",
        "F77",
        "FACTURE ACHAT",
    ]
    assert body["resume"]["nb_ignorees"] == len(body["lignes_ignorees"])


# --- Gros fichiers : 50 000 lignes au plus (08/10/2026) -------------------------------------------


def _big_export(rows: int) -> bytes:
    return big_xlsx(
        HEADER,
        rows,
        lambda index: [
            date(2025, 9, 2),
            "BQ1",
            "5141",
            f"P{index}",
            "REG",
            index + 1,
            None,
            None,
            None,
        ],
    )


def test_an_export_of_50001_lines_is_refused(client, comptable, db, journals):
    response = analyse(client, comptable, db, _big_export(50_001))

    assert response.status_code == 409
    assert response.json() == {"detail": "Fichier trop long : 50 000 lignes au plus par fichier."}


def test_already_imported_entries_are_found_across_hash_batches(
    client, comptable, db, journals, monkeypatch
):
    monkeypatch.setattr(accounting_repository, "HASH_BATCH", 2)
    content = _big_export(5)
    post(client, CONFIRM, comptable, db, content)

    body = analyse(client, comptable, db, content).json()

    assert {line["statut"] for line in body["lignes"]} == {"Doublon"}
    assert len(body["lignes"]) == 5
