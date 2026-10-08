"""Lecture commune d'un classeur d'import (relevés et exports comptables)."""

from datetime import date, datetime
from io import BytesIO

import pytest
from openpyxl import Workbook

from app.services.errors import ConflictError
from app.services.import_file import (
    ImportField,
    check_file,
    columns_of,
    detect_header,
    field_for_header,
    headers_of,
    mapping_errors,
    mapping_from_headers,
    propose_mapping,
    read_sheet,
)
from app.services.import_service import STATEMENT_FIELDS
from app.services.normalization_service import normalize_header
from tests.helpers import big_xlsx, xls

FIELDS = (
    ImportField("date", "Date", True, ("date",)),
    ImportField("libelle", "Libellé", True, ("libelle",)),
    ImportField("debit", "Débit", False, ("debit",)),
    ImportField("credit", "Crédit", False, ("credit",)),
    ImportField("montant", "Montant signé", False, ("montant",)),
)


def xlsx(rows: list[list]) -> bytes:
    workbook = Workbook()
    for row in rows:
        workbook.active.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_header_is_detected_below_title_lines():
    _, _, rows = read_sheet(xlsx([["Titre"], [], ["Date", "Libellé", "Débit"], [1, "x", 2]]), None)

    assert detect_header(rows, FIELDS) == 2


def test_mapping_is_proposed_from_synonyms():
    _, _, rows = read_sheet(xlsx([["Date", "Libellé", "Crédit"], ["01/09/2025", "VIR", 5]]), None)
    columns = columns_of(rows[0], rows[1:])

    assert propose_mapping(columns, FIELDS) == {
        "date": 0,
        "libelle": 1,
        "debit": None,
        "credit": 2,
        "montant": None,
    }


def test_saved_headers_must_all_be_found():
    _, _, rows = read_sheet(xlsx([["Date", "Libellé", "Débit"]]), None)
    columns = columns_of(rows[0], [])

    assert mapping_from_headers({"date": "Date", "debit": "Débit"}, columns, FIELDS)["debit"] == 2
    assert mapping_from_headers({"date": "Date", "credit": "Crédit"}, columns, FIELDS) is None


def test_headers_to_remember_need_a_title_on_every_mapped_column():
    _, _, rows = read_sheet(xlsx([["Date", None, "Débit"], ["01/09/2025", "VIR", 3]]), None)
    columns = columns_of(rows[0], rows[1:])

    assert headers_of({"date": 0, "debit": 2, "libelle": None}, columns) == {
        "date": "Date",
        "debit": "Débit",
    }
    assert headers_of({"date": 0, "libelle": 1}, columns) is None


def test_mapping_errors_name_the_missing_and_conflicting_fields():
    errors = mapping_errors({"date": 0, "libelle": None, "debit": 1, "montant": 1}, 3, FIELDS)

    assert "Colonne obligatoire non associée : Libellé." in errors
    assert "Choisissez Débit et Crédit, ou Montant signé, pas les deux." in errors
    assert "La colonne B est associée à plusieurs champs." in errors


@pytest.mark.parametrize(
    ("nom", "content", "message"),
    [
        ("export.csv", b"x", "Seuls les fichiers Excel .xlsx ou .xls sont acceptés."),
        ("export.xlsx", b"", "Le fichier est vide."),
        ("export.xlsx", b"x" * (20 * 1024 * 1024 + 1), "Fichier trop volumineux : 20 Mo au plus."),
    ],
)
def test_check_file_refuses_wrong_files(nom, content, message):
    with pytest.raises(ConflictError, match=message):
        check_file(nom, content)


# --- Ancien format .xls (08/10/2026) ---------------------------------------------------------------


def test_xls_file_names_are_accepted():
    check_file("RELEVE.XLS", b"x")
    check_file("export.xls", b"x")


def test_xls_is_read_like_the_same_xlsx():
    rows = [
        ["Relevé BP"],
        [],
        ["Date", "Libellé", "Débit", "Crédit"],
        [date(2025, 9, 2), "VIR CLIENT", None, 1250.5],
        [date(2025, 9, 3), "COMMISSION", 20, None],
        ["03/09/2025", "TEXTE", "1 000,00", None],
    ]

    names_xls, name_xls, from_xls = read_sheet(xls(("Feuil1", rows)), None)
    _, _, from_xlsx = read_sheet(xlsx(rows), None)

    assert (names_xls, name_xls) == (["Feuil1"], "Feuil1")

    # Mêmes valeurs ; seules les lignes vides diffèrent de longueur (le .xls n'a pas de cellule)
    def trim(row):
        values = list(row)
        while values and values[-1] is None:
            values.pop()
        return values

    assert [trim(row) for row in from_xls] == [trim(row) for row in from_xlsx]
    assert from_xls[3][0] == datetime(2025, 9, 2)
    assert from_xls[4][2] == 20


def test_xls_sheet_is_chosen_by_name():
    content = xls(("Résumé", [["x"]]), ("Opérations", [["Date", "Libellé"], ["01/09/2025", "VIR"]]))

    names, name, rows = read_sheet(content, "Opérations")

    assert (names, name, rows[1]) == (["Résumé", "Opérations"], "Opérations", ("01/09/2025", "VIR"))
    with pytest.raises(ConflictError, match="Feuille introuvable"):
        read_sheet(content, "Absente")


def test_unreadable_xls_gives_a_clear_message():
    damaged = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64

    with pytest.raises(ConflictError, match=".xlsx ou .xls valide"):
        read_sheet(damaged, None)


# --- Gros fichiers : 50 000 lignes au plus (08/10/2026) -------------------------------------------


def test_a_sheet_of_50000_lines_is_read_and_one_more_is_refused():
    def row(index):
        return ["01/09/2025", f"VIR {index}", index + 1]

    _, _, rows = read_sheet(big_xlsx(["Date", "Libellé", "Débit"], 50_000, row), None)
    assert len(rows) == 50_001  # en-tête + 50 000 lignes

    too_long = big_xlsx(["Date", "Libellé", "Débit"], 50_000 + 31, row)
    with pytest.raises(ConflictError, match="50 000 lignes au plus"):
        read_sheet(too_long, None)


# --- Abréviations des en-têtes (08/10/2026) --------------------------------------------------------

STATEMENT_HEADERS = (
    ImportField("date_operation", "Date d'opération", True, ("date operation", "date op", "date")),
    ImportField("date_valeur", "Date de valeur", False, ("date valeur", "valeur")),
    ImportField("libelle", "Libellé", True, ("libelle", "operation")),
    ImportField("debit", "Débit", False, ("debit", "montant debit")),
    ImportField("credit", "Crédit", False, ("credit",)),
    ImportField("montant", "Montant signé", False, ("montant",)),
)


@pytest.mark.parametrize(
    ("entete", "expected"),
    [
        ("DT opération", ("date_operation", 2)),  # relevé Attijariwafa
        ("DT valeur", ("date_valeur", 2)),
        ("Libellé large", ("libelle", 1)),  # commence par « Libellé »
        ("Lib", ("libelle", 2)),
        ("Mnt", ("montant", 2)),
        ("Mt débit", ("debit", 2)),  # « montant debit »
        ("Déb", ("debit", 2)),
        ("Cred", ("credit", 2)),
        ("DTX", (None, 0)),  # une abréviation se lit en mot entier seulement
    ],
)
def test_common_abbreviations_are_understood(entete, expected):
    assert field_for_header(normalize_header(entete), STATEMENT_HEADERS) == expected


def test_awb_statement_headers_are_detected():
    content = xlsx(
        [
            ["ATTIJARIWAFA BANK"],
            [
                None,
                "DT opération",
                None,
                None,
                "DT valeur",
                None,
                "Libellé large",
                "Débit",
                "Crédit",
            ],
            [
                None,
                "06/10/2026",
                None,
                None,
                "06/10/2026",
                None,
                "PAIEMENT CHEQUE 6723309",
                500,
                None,
            ],
        ]
    )
    _, _, rows = read_sheet(content, None)
    index = detect_header(rows, STATEMENT_FIELDS)
    mapping = propose_mapping(columns_of(rows[index], rows[index + 1 :]), STATEMENT_FIELDS)

    assert index == 1
    assert (mapping["date_operation"], mapping["date_valeur"], mapping["libelle"]) == (1, 4, 6)
    assert (mapping["debit"], mapping["credit"]) == (7, 8)
