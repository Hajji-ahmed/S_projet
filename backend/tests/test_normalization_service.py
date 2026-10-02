"""Normalisation des valeurs lues dans un fichier importé : fonctions pures."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from app.services.normalization_service import (
    balance_line_kind,
    clean_libelle,
    extract_reference,
    guess_pointage,
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


@pytest.mark.parametrize(
    ("libelle", "debit", "credit", "expected"),
    [
        ("COMMISSION BANCAIRE", "250", None, "FRAIS_BANCAIRES"),
        ("AGIOS / FRAIS DE FINANCEMENT", "690", None, "FRAIS_BANCAIRES"),
        ("frais tenue de compte", "150", None, "FRAIS_BANCAIRES"),
        ("COMMISSIONS SUR REMISE", None, "5", "FRAIS_BANCAIRES"),  # le mot-clé passe avant le sens
        ("VIR CLIENT ATLAS TEXTILE", None, "45000", "ENCAISSEMENT"),
        ("REMISE CHÈQUES CLIENTS", None, "20000", "ENCAISSEMENT"),
        ("VIR FOURNISSEUR ABC", "18000", None, "DECAISSEMENT"),
        ("PRÉLÈVEMENT ASSURANCE", "3200", None, "DECAISSEMENT"),
        ("CHQ N°458721", "12500", None, "DECAISSEMENT"),
        ("FRAISIER SA", None, "10", "ENCAISSEMENT"),  # mot entier seulement
        ("SANS MONTANT", None, None, None),
    ],
)
def test_pointage_is_guessed_from_label_then_direction(libelle, debit, credit, expected):
    amount = lambda value: None if value is None else Decimal(value)  # noqa: E731

    assert guess_pointage(libelle, amount(debit), amount(credit)) == expected


@pytest.mark.parametrize(
    ("libelle", "kind"),
    [
        ("SOLDE INITIAL", "ouverture"),
        ("Solde précédent au 31/08", "ouverture"),
        ("ANCIEN  SOLDE", "ouverture"),
        ("REPORT", "ouverture"),
        ("SOLDE FINAL", "cloture"),
        ("Nouveau solde", "cloture"),
        ("VIR SOLDE INITIAL CLIENT", None),  # doit commencer par le mot-clé
        ("FRAIS", None),
        (None, None),
    ],
)
def test_balance_lines_are_recognised(libelle, kind):
    assert balance_line_kind(libelle) == kind


def test_line_hash_is_stable_and_separates_identical_lines():
    parts = (date(2026, 9, 30), "FRAIS", Decimal("10.00"))

    assert line_hash(1, parts, 1) == line_hash(1, parts, 1)
    assert line_hash(1, parts, 1) != line_hash(1, parts, 2)  # deux frais identiques le même jour
    assert line_hash(1, parts, 1) != line_hash(2, parts, 1)  # même ligne, autre compte
