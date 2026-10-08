"""Normalisation des valeurs lues dans un fichier importé : fonctions pures."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from app.services.normalization_service import (
    balance_line_kind,
    clean_libelle,
    extract_reference,
    guess_pointage,
    label_key,
    line_hash,
    normalize_header,
    parse_amount,
    parse_date,
    pointage_code,
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


CATEGORIES = (
    "A voir",
    "AGIOS",
    "AGIOS D'ECHELLE",
    "CNSS",
    "VIR CNSS",
    "COM",
    "FRAIS",
    "FRAIS D'APPROCHE",
    "LA PAIE",
    "INTERET",
    "RESTITUTION INTERETS DEBITEURS/FC",
    "REMBOURSEMENT PRÊT",
    "SIMTIS-TEFIL",
    "TVA",
)


@pytest.mark.parametrize(
    ("libelle", "expected"),
    [
        ("AGIOS TRIMESTRE 3", "AGIOS"),
        ("Agios d'échelle T3", "AGIOS D'ECHELLE"),  # le plus long nom gagne
        ("VIR CNSS SEPTEMBRE", "VIR CNSS"),
        ("PRLV CNSS", "CNSS"),
        ("COMMISSION SUR REMISE", "COM"),  # synonyme
        ("COM/VIREMENT", "COM"),  # la ponctuation sépare les mots
        ("FRAIS TENUE DE COMPTE", "FRAIS"),
        ("FRAIS D'APPROCHE IMPORT", "FRAIS D'APPROCHE"),
        ("VIR SALAIRES SEPT", "LA PAIE"),
        ("INTERETS DEBITEURS", "INTERET"),
        ("RESTITUTION INTERETS DEBITEURS/FC", "RESTITUTION INTERETS DEBITEURS/FC"),
        ("REMBOURSEMENT PRET 12", "REMBOURSEMENT PRÊT"),
        ("VIREMENT SIMTIS TEFIL", "SIMTIS-TEFIL"),
        ("COMPTE COURANT", None),  # « COM » en mot entier seulement
        ("FRAISIER SA", None),
        ("A VOIR AVEC LA BANQUE", None),  # « A voir » n'est jamais automatique
        ("VIR CLIENT ATLAS", None),
        ("", None),
        (None, None),
    ],
)
def test_pointage_is_the_category_named_in_the_label(libelle, expected):
    assert guess_pointage(libelle, CATEGORIES) == expected


def test_label_key_and_code_ignore_accents_case_and_punctuation():
    assert label_key("  Agios d'échelle ") == "AGIOS D ECHELLE"
    assert pointage_code("ENCAISSEMENT HORS GROUP/DECATHLON") == "ENCAISSEMENT_HORS_GROUP_DECATHLON"
    assert pointage_code("REMBOURSEMENT PRÊT") == "REMBOURSEMENT_PRET"


def test_the_74_categories_have_distinct_codes_that_fit_the_column():
    from app.seeds.pointages import CATEGORIES_POINTAGE

    codes = [pointage_code(libelle) for libelle in CATEGORIES_POINTAGE]
    assert len(CATEGORIES_POINTAGE) == 74
    assert len(set(codes)) == 74
    assert max(len(code) for code in codes) <= 60


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
