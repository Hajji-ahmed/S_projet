"""Normalisation des valeurs lues dans un fichier importé : fonctions pures."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from app.services.normalization_service import (
    clean_libelle,
    extract_reference,
    line_hash,
    normalize_header,
    parse_amount,
    parse_date,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1 250 000,50", "1250000.50"),
        ("1 250 000,50", "1250000.50"),
        ("1.250.000,50", "1250000.50"),
        ("1,250,000.50", "1250000.50"),
        ("1250.5", "1250.50"),
        ("-1 250,50", "-1250.50"),
        ("(1 250,50)", "-1250.50"),
        ("1 250,50-", "-1250.50"),
        ("−15", "-15.00"),
        ("+3", "3.00"),
        ("1 250,50 DH", "1250.50"),
        ("EUR 12", "12.00"),
        (5, "5.00"),
        (1250.5, "1250.50"),
        (0.1 + 0.2, "0.30"),  # résidu binaire d'un calcul Excel
        (Decimal("7.1"), "7.10"),
    ],
)
def test_amounts_are_read_exactly(value, expected):
    assert parse_amount(value) == Decimal(expected)
    assert str(parse_amount(value)) == expected


@pytest.mark.parametrize("value", [None, "", "   "])
def test_blank_amount_is_none(value):
    assert parse_amount(value) is None


@pytest.mark.parametrize(
    "value", ["abc", "12,345", "1.234", "1 2 3,4,5.6.7", "12 000 000 000 000 000 000", True]
)
def test_unreadable_amount_is_refused(value):
    with pytest.raises(ValueError):
        parse_amount(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (datetime(2026, 9, 30, 14, 5), date(2026, 9, 30)),
        (date(2026, 9, 30), date(2026, 9, 30)),
        ("30/09/2026", date(2026, 9, 30)),
        ("30-09-2026", date(2026, 9, 30)),
        ("30.09.26", date(2026, 9, 30)),
        ("2026-09-30", date(2026, 9, 30)),
        ("30/09/2026 00:00:00", date(2026, 9, 30)),
        (45658, date(2025, 1, 1)),  # numéro de série Excel
    ],
)
def test_dates_are_read(value, expected):
    assert parse_date(value) == expected


@pytest.mark.parametrize("value", ["31/02/2026", "hier", "2026/30/09", -3])
def test_unreadable_date_is_refused(value):
    with pytest.raises(ValueError):
        parse_date(value)


def test_headers_are_compared_without_case_accents_or_punctuation():
    assert normalize_header("Date d'opération") == "date d operation"
    assert normalize_header("  DÉBIT (MAD) ") == "debit mad"
    assert normalize_header(None) == ""


def test_label_is_cleaned_and_uppercased():
    assert clean_libelle("  vir   reçu  client ") == "VIR REÇU CLIENT"
    assert clean_libelle("  ") is None


@pytest.mark.parametrize(
    ("libelle", "reference"),
    [
        ("CHQ N° 1234567 FOURNISSEUR", "1234567"),
        ("REMISE CHEQUE 0045678", "0045678"),
        ("VIR RECU REF: AB-123/45 CLIENT", "AB-123/45"),
        ("REG FACT-458 CLIENT ABC", "FACT-458"),
        ("FRAIS TENUE DE COMPTE", None),
        (None, None),
    ],
)
def test_reference_is_extracted_from_the_label(libelle, reference):
    assert extract_reference(libelle) == reference


def test_line_hash_is_stable_and_separates_identical_lines():
    parts = (date(2026, 9, 30), "FRAIS", Decimal("10.00"))

    assert line_hash(1, parts, 1) == line_hash(1, parts, 1)
    assert line_hash(1, parts, 1) != line_hash(1, parts, 2)  # deux frais identiques le même jour
    assert line_hash(1, parts, 1) != line_hash(2, parts, 1)  # même ligne, autre compte
