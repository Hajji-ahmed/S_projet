"""Règles transverses sur les modèles : l'argent est exact, jamais approximatif."""

from sqlalchemy import Float, Numeric

from app.models import Base

# Montants (18,2), taux (18,6), score de rapprochement (5,2), poids d'un critère (6,2)
ALLOWED_NUMERIC = {(18, 2), (18, 6), (5, 2), (6, 2)}


def all_columns():
    return [
        (table.name, column) for table in Base.metadata.tables.values() for column in table.columns
    ]


def test_no_column_uses_floating_point():
    floats = [
        f"{table}.{column.name}"
        for table, column in all_columns()
        if isinstance(column.type, Float)
    ]

    assert floats == []


def test_numeric_columns_use_expected_precisions():
    unexpected = [
        f"{table}.{column.name} = NUMERIC({column.type.precision},{column.type.scale})"
        for table, column in all_columns()
        if isinstance(column.type, Numeric)
        and (column.type.precision, column.type.scale) not in ALLOWED_NUMERIC
    ]

    assert unexpected == []


def test_money_columns_are_numeric_18_2():
    money = {
        ("bank_accounts", "credit_autorise"),
        ("bank_account_balances", "solde"),
        ("bank_account_balances", "credit_utilise"),
        ("bank_transactions", "debit"),
        ("bank_transactions", "credit"),
        ("bank_transactions", "montant"),
        ("accounting_entries", "montant"),
        ("cash_forecasts", "montant"),
        ("discrepancies", "montant"),
    }
    tables = Base.metadata.tables

    for table, name in money:
        column_type = tables[table].columns[name].type
        assert (column_type.precision, column_type.scale) == (18, 2), f"{table}.{name}"


def test_rates_are_numeric_18_6():
    tables = Base.metadata.tables

    for table, name in (("bank_accounts", "taux_interet"), ("exchange_rates", "taux")):
        column_type = tables[table].columns[name].type
        assert (column_type.precision, column_type.scale) == (18, 6), f"{table}.{name}"
