"""Normalisation des valeurs lues dans un fichier importé : fonctions pures."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from app.services.normalization_service import (
    CREDIT,
    DEBIT,
    balance_line_kind,
    cle_doublon,
    cle_memoire,
    clean_libelle,
    extract_reference,
    guess_pointage,
    label_key,
    line_hash,
    normalize_header,
    parse_amount,
    parse_date,
    pointage_code,
    sens_categorie,
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


@pytest.mark.parametrize("value", ["-", " - ", "–", "—"])
def test_dash_date_is_empty(value):
    """BP (05/11/2026) : une opération en cours « (*) » a « - » en date de valeur."""
    assert parse_date(value) is None


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


TIMBRE = "Droit de timbre décaissé"
COMMISSIONS = "Commissions et frais bancaires décaissé"
TVA = "Tva/commissions et frais bancaires décaissé"


@pytest.mark.parametrize(
    ("libelle", "sens", "expected"),
    [
        # Mots-clés sûrs (16/11/2026), dans l'ordre de priorité
        ("TAXE SUR VALEUR AJOUTEE", DEBIT, TVA),
        ("TVA SUR COMMISSION", DEBIT, TVA),  # la TVA passe avant la commission
        ("DROITS DE TIMBRE", DEBIT, TIMBRE),
        ("DT D'ENREGISTREMENT", DEBIT, TIMBRE),
        ("TIMBRE/REM LCN REF 1234", DEBIT, TIMBRE),
        ("FRAIS DE TIMBRE", DEBIT, TIMBRE),  # le timbre passe avant les frais
        ("AGIOS D'ESCOMPTE T3", DEBIT, "Agios d'escompte décaissé"),
        ("AGIOS TRIMESTRE 3", DEBIT, "Agios d'échelle décaissé"),
        ("COMMISSION SUR REMISE", DEBIT, COMMISSIONS),
        ("COM/VIREMENT", DEBIT, COMMISSIONS),  # la ponctuation sépare les mots
        ("COM.ADOBE", DEBIT, COMMISSIONS),
        ("FRAIS TENUE DE COMPTE", DEBIT, COMMISSIONS),
        ("PRLV CNSS SEPTEMBRE", DEBIT, "Charges sociales décaissé"),
        ("VIREMENT DGI IS", DEBIT, "Impôts et taxes DGI décaissé"),
        ("COMMISSION SUR REMISE", None, COMMISSIONS),  # sens inconnu : toutes les catégories
        # Une catégorie « … décaissé » ne va pas à un crédit (16/11/2026)
        ("RESTITUTION COMMISSION", CREDIT, None),
        ("AGIOS RESTITUES", CREDIT, None),
        # Le nom d'une catégorie dans le libellé, avec le sens
        ("VIREMENT CLIENT ENCAISSE", CREDIT, "Virement client encaissé"),
        ("VIREMENT CLIENT ENCAISSE", DEBIT, None),
        ("COMPTE COURANT", DEBIT, None),  # « COM » en mot entier seulement
        # Une fin d'adresse web ne compte pas (11/11/2026) : « STE.BIS.COM » n'est pas une COM
        ("CHEQUE N 5100983 REMIS PAR CAM EN FAVEUR DE STE.BIS.COM", DEBIT, None),
        ("PAIEMENT SITE.MA", DEBIT, None),
        ("FRAISIER SA", DEBIT, None),
        # « À analyser » et « Solde à nouveau » ne sont jamais automatiques
        ("A ANALYSER AVEC LA BANQUE", DEBIT, None),
        ("SOLDE A NOUVEAU", CREDIT, None),
        ("VIR CLIENT ATLAS", CREDIT, None),
        ("", DEBIT, None),
        (None, None, None),
    ],
)
def test_pointage_comes_from_a_category_name_or_a_safe_keyword(libelle, sens, expected):
    from app.seeds.pointages import CATEGORIES_POINTAGE

    assert guess_pointage(libelle, CATEGORIES_POINTAGE, sens) == expected


def test_old_categories_are_never_guessed_once_inactive():
    """La liste ne reçoit que les catégories actives : sans la nouvelle, rien n'est proposé."""
    assert guess_pointage("COMMISSION SUR REMISE", ("COM", "FRAIS"), DEBIT) is None


@pytest.mark.parametrize(
    ("libelle", "cle"),
    [
        ("CHQ 5100983 REMIS PAR SOFT RETAIL", "CHQ REMIS PAR SOFT RETAIL"),
        ("Chq 5100990 remis par Soft-Retail", "CHQ REMIS PAR SOFT RETAIL"),
        ("VIR RECU 01/10/2026 REF20261001 ATLAS", "VIR RECU ATLAS"),
        ("FRAIS 3T2026", "FRAIS"),
        ("123456 01/10", ""),
        (None, ""),
    ],
)
def test_memory_key_ignores_words_with_digits(libelle, cle):
    assert cle_memoire(libelle) == cle


def test_category_direction_comes_from_its_last_word():
    assert sens_categorie("Virement fournisseur décaissé") == DEBIT
    assert sens_categorie("Autres valeurs décaissées") == DEBIT
    assert sens_categorie("Chèque client encaissé") == CREDIT
    assert sens_categorie("Autres valeurs encaissées") == CREDIT
    assert sens_categorie("Effet client escompté") is None
    assert sens_categorie("À analyser") is None


def test_label_key_and_code_ignore_accents_case_and_punctuation():
    assert label_key("  Agios d'échelle ") == "AGIOS D ECHELLE"
    assert pointage_code("ENCAISSEMENT HORS GROUP/DECATHLON") == "ENCAISSEMENT_HORS_GROUP_DECATHLON"
    assert pointage_code("REMBOURSEMENT PRÊT") == "REMBOURSEMENT_PRET"


def test_the_pointage_list_has_distinct_codes_that_fit_the_column():
    """Liste du 16/11/2026 : 46 catégories + « À analyser », aucun code repris de l'ancienne."""
    from app.seeds.pointages import ANCIENNES_CATEGORIES, CATEGORIES_POINTAGE

    codes = [pointage_code(libelle) for libelle in CATEGORIES_POINTAGE]
    assert len(CATEGORIES_POINTAGE) == 47
    assert len(set(codes)) == 47
    assert max(len(code) for code in codes) <= 60
    assert CATEGORIES_POINTAGE[-1] == "À analyser"
    assert not set(codes) & {pointage_code(libelle) for libelle in ANCIENNES_CATEGORIES}


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


def test_solde_au_lines_are_recognised():
    from app.services.normalization_service import is_solde_au

    assert is_solde_au("SOLDE AU 31/12/2024")
    assert is_solde_au("  solde au 31/12/2024 ")
    assert not is_solde_au("SOLDE AUTOMATIQUE")
    assert not is_solde_au("VIR SOLDE AU CLIENT")
    assert not is_solde_au(None)


def test_a_starred_amount_of_a_pending_operation_is_read():
    """21/10/2026 : BMCE marque d'une étoile le montant d'une opération en cours."""
    assert parse_amount("213,68*") == Decimal("213.68")
    assert parse_amount("927.349,01*") == Decimal("927349.01")
    assert parse_amount("1.500.000,00 *") == Decimal("1500000.00")


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("PAIEMENT CHEQUE N° 0000271", "PAIEMENT CHEQUE N 0000271"),
        ("COM & FRAIS REGLEMENT 3 LCN", "COM   FRAIS REGLEMENT    3 LCN"),
        ("Virement reçu de Mr Malali", "VIREMENT RECU DE MR MALALI"),
        ("VIR.WEB RECU DE CHATER", "VIR WEB RECU DE CHATER"),
    ],
)
def test_two_labels_written_differently_by_the_bank_share_one_duplicate_key(a, b):
    """13/11/2026 : « N° » / « N », « & » présent ou absent, accents et ponctuation ne comptent pas."""
    assert cle_doublon(a) == cle_doublon(b)


def test_the_duplicate_key_keeps_the_words_and_numbers_that_tell_operations_apart():
    assert cle_doublon("PAIEMENT CHEQUE N 0000271") != cle_doublon("PAIEMENT CHEQUE N 0000272")
    assert cle_doublon(None) == ""
