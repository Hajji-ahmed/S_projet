"""Lecture commune d'un classeur d'import (relevés et exports comptables)."""

from io import BytesIO

import pytest
from openpyxl import Workbook

from app.services.errors import ConflictError
from app.services.import_file import (
    ImportField,
    check_file,
    columns_of,
    detect_header,
    headers_of,
    mapping_errors,
    mapping_from_headers,
    propose_mapping,
    read_sheet,
)

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
        ("export.csv", b"x", "Seuls les fichiers Excel .xlsx sont acceptés."),
        ("export.xlsx", b"", "Le fichier est vide."),
        ("export.xlsx", b"x" * (5 * 1024 * 1024 + 1), "Fichier trop volumineux : 5 Mo au plus."),
    ],
)
def test_check_file_refuses_wrong_files(nom, content, message):
    with pytest.raises(ConflictError, match=message):
        check_file(nom, content)
