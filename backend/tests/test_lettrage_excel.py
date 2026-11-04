"""Lettrage côte à côte (04/11/2026) : règle pure de mise en face (`lettrage_excel.en_face`)."""

from datetime import date

from app.services.lettrage_excel import en_face


def jour(n: int) -> date:
    return date(2026, 9, n)


def lignes(operations, ecritures):
    """Opérations et écritures en (libellé, montant, jour) ; l'écriture est de signe opposé."""
    return [
        (op and op[0], ec and ec[0])
        for op, ec in en_face(
            operations,
            ecritures,
            lambda op: op[1],
            lambda ec: -ec[1],
            lambda op: jour(op[2]),
            lambda ec: jour(ec[2]),
        )
    ]


def test_an_operation_faces_the_entry_of_the_same_amount_first():
    operations = [("VIR A", 100, 1), ("VIR B", 250, 2)]
    ecritures = [("REG B", -250, 1), ("REG A", -100, 3)]

    assert lignes(operations, ecritures) == [("VIR A", "REG A"), ("VIR B", "REG B")]


def test_what_is_left_faces_in_date_order_and_a_longer_side_leaves_blanks():
    operations = [("VIR KARIM", 3000, 10)]
    ecritures = [("REG KARIM 2", -2000, 11), ("REG KARIM 1", -1000, 10)]

    assert lignes(operations, ecritures) == [("VIR KARIM", "REG KARIM 1"), (None, "REG KARIM 2")]


def test_extra_operations_are_left_alone():
    operations = [("CHEQUE", 12450, 5), ("COMMISSION", -175, 5), ("TVA", -25, 5)]
    ecritures = [("CHQ FOURNISSEUR", -12250, 5)]

    assert lignes(operations, ecritures) == [
        ("CHEQUE", "CHQ FOURNISSEUR"),
        ("COMMISSION", None),
        ("TVA", None),
    ]


def test_two_entries_of_the_same_amount_are_used_once_each():
    operations = [("VERS 1", 500, 1), ("VERS 2", 500, 2)]
    ecritures = [("ESP 1", -500, 1), ("ESP 2", -500, 2)]

    assert lignes(operations, ecritures) == [("VERS 1", "ESP 1"), ("VERS 2", "ESP 2")]


def test_rows_are_sorted_by_date():
    operations = [("TARD", 100, 20), ("TOT", 999, 2)]
    ecritures = [("REG TARD", -100, 20), ("REG TOT", -900, 3)]

    assert lignes(operations, ecritures) == [("TOT", "REG TOT"), ("TARD", "REG TARD")]


def test_an_entry_of_a_currency_account_is_written_in_that_currency():
    from decimal import Decimal
    from types import SimpleNamespace

    from app.services.lettrage_excel import debit_credit

    sage_debit = SimpleNamespace(
        debit=Decimal("10950.00"), credit=Decimal("0"), montant_devise=Decimal("-1000.00")
    )
    sans_devise = SimpleNamespace(debit=Decimal("0"), credit=Decimal("500.00"), montant_devise=None)

    assert debit_credit(sage_debit, "EUR") == (Decimal("1000.00"), Decimal("0.00"))
    assert debit_credit(sage_debit, "MAD") == (Decimal("10950.00"), Decimal("0"))
    assert debit_credit(sans_devise, "EUR") == (Decimal("0"), Decimal("500.00"))
