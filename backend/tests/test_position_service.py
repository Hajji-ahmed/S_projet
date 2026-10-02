"""Calculs de position : formules du CDC, valeurs inconnues, dernières valeurs connues."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.services.position_service import (
    LatestValues,
    account_figures,
    credit_disponible,
    latest_values,
    position_disponible,
)

D = Decimal


@dataclass
class Balance:
    date_solde: date
    solde: Decimal | None = None
    credit_utilise: Decimal | None = None


def test_cdc_example():
    """CDC §5.2 : solde 300 000, autorisé 500 000, utilisé 100 000 → 400 000 puis 700 000."""
    figures = account_figures(
        D("500000"),
        LatestValues(solde=D("300000"), credit_utilise=D("100000"), date_maj=date(2026, 9, 30)),
    )

    assert figures.credit_disponible == D("400000")
    assert figures.position_disponible == D("700000")


def test_overdraft_gives_a_negative_available_credit():
    assert credit_disponible(D("100000"), D("150000.50")) == D("-50000.50")


def test_negative_balance_is_kept():
    assert position_disponible(D("-20000"), D("50000")) == D("30000")


def test_unknown_used_credit_gives_unknown_results():
    figures = account_figures(
        D("500000"), LatestValues(solde=D("1"), credit_utilise=None, date_maj=None)
    )

    assert figures.credit_disponible is None
    assert figures.position_disponible is None
    assert figures.solde == D("1")


def test_unknown_balance_gives_unknown_position_but_known_available_credit():
    figures = account_figures(
        D("500000"), LatestValues(solde=None, credit_utilise=D("0"), date_maj=None)
    )

    assert figures.credit_disponible == D("500000")
    assert figures.position_disponible is None


def test_amounts_stay_exact():
    assert position_disponible(D("0.10"), credit_disponible(D("0.30"), D("0.10"))) == D("0.30")


def test_latest_values_are_taken_field_by_field():
    balances = [
        Balance(date(2026, 9, 28), solde=D("100"), credit_utilise=D("10")),
        Balance(date(2026, 9, 29), credit_utilise=D("20")),
        Balance(date(2026, 9, 30), solde=D("300")),
    ]

    latest = latest_values(balances)

    assert latest == LatestValues(
        solde=D("300"), credit_utilise=D("20"), date_maj=date(2026, 9, 30)
    )


def test_latest_values_ignore_dates_after_the_reference_day():
    balances = [
        Balance(date(2026, 9, 29), solde=D("100")),
        Balance(date(2026, 10, 2), solde=D("999")),
    ]

    assert latest_values(balances, as_of=date(2026, 9, 30)).solde == D("100")


def test_no_balance_at_all():
    assert latest_values([]) == LatestValues(solde=None, credit_utilise=None, date_maj=None)
