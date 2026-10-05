"""Calculs de position : formules du CDC, valeurs inconnues, dernières valeurs connues."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.services.position_service import (
    BanqueColonne,
    Cellule,
    LatestValues,
    account_figures,
    credit_disponible,
    depassement,
    facilite_de_caisse,
    fusion_soldes,
    latest_values,
    ligne_devise,
    position_disponible,
    tableau_banques,
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


# --- Tableau Banques (P8.1) ------------------------------------------------------------------------

# Dates passées : aucun résultat ne dépend de la date du jour
J26, J27, J28, J29, J30 = (date(2025, 9, d) for d in (26, 27, 28, 29, 30))


def colonne(bank_id, ligne="0", soldes=(), *, compte=True, taux=None) -> BanqueColonne:
    return BanqueColonne(
        bank_id=bank_id,
        code=f"B{bank_id}",
        logo=None,
        bank_account_id=100 + bank_id if compte else None,
        taux_interet=D(taux) if taux else None,
        ligne=D(ligne) if compte else None,
        soldes=tuple((jour, D(solde)) for jour, solde in soldes),
    )


def test_facilite_de_caisse_is_balance_plus_ligne():
    assert facilite_de_caisse(D("-200000"), D("500000")) == D("300000")


def test_depassement_is_total_minus_lignes_and_unknown_without_total():
    assert depassement(D("700000"), D("800000")) == D("-100000")
    assert depassement(None, D("800000")) is None


def test_validated_example():
    """Décision du 02/10/2026 : 300 000 + 400 000 = 700 000 ; 700 000 − 800 000 = −100 000."""
    awb = colonne(1, "500000", [(J30, "-200000")])
    bmce = colonne(2, "300000", [(J30, "100000")])

    table = tableau_banques([awb, bmce], J30)

    [jour] = table.jours
    assert jour.date == J30
    assert jour.ligne.cellules == (
        Cellule(1, D("300000"), J30, False),
        Cellule(2, D("400000"), J30, False),
    )
    assert jour.ligne.total == D("700000")
    assert jour.ligne.depassement == D("-100000")
    assert table.ligne_total == D("800000")
    assert table.date_fin == J30


def test_disponible_is_last_facilite_minus_ligne():
    """Décision du 03/10/2026 : Disponible Fc reel = facilité de caisse du dernier jour − LIGNE ;
    TOTAL = somme ; DEPASSEMENT = TOTAL, la LIGNE étant déjà retirée (correction du 03/10/2026)."""
    awb = colonne(1, "800000", [(J30, "400000")])
    bp = colonne(3, "600000", [(J30, "650000")])

    table = tableau_banques([awb, bp], J30)

    facilite = table.jours[-1].ligne
    assert [c.valeur for c in facilite.cellules] == [D("1200000"), D("1250000")]
    assert (facilite.total, facilite.depassement) == (D("2450000"), D("1050000"))
    assert table.disponible.cellules == (
        Cellule(1, D("400000"), J30, False),
        Cellule(3, D("650000"), J30, False),
    )
    assert table.disponible.total == D("1050000")
    assert table.disponible.depassement == D("1050000")
    # Même valeur que le DEPASSEMENT de la facilité de caisse du dernier jour
    assert table.disponible.depassement == facilite.depassement


def test_disponible_keeps_the_carried_forward_balance_and_skips_unknown_banks():
    awb = colonne(1, "100", [(J28, "10")])
    bp = colonne(3, "200")  # compte sans aucun solde

    table = tableau_banques([awb, bp], J30)

    assert table.disponible.cellules == (
        Cellule(1, D("10"), J28, True),
        Cellule(3, None, None, False),
    )
    assert table.disponible.total == D("10")
    assert table.disponible.depassement == D("10")  # = TOTAL


def test_operation_balance_wins_over_the_day_balance():
    """Décision du 03/10/2026 : solde de la dernière opération du jour, sinon solde du jour."""
    operations = [(J30, D("5"))]
    saisies = [(J29, D("7")), (J30, D("9"))]

    assert fusion_soldes(operations, saisies) == ((J29, D("7")), (J30, D("5")))
    assert fusion_soldes([], saisies) == ((J29, D("7")), (J30, D("9")))
    assert fusion_soldes(operations, []) == ((J30, D("5")),)


def test_a_day_without_balance_reuses_the_last_known_one():
    awb = colonne(1, "100", [(J28, "10"), (J30, "30")])
    bmce = colonne(2, "200", [(J28, "20")])

    table = tableau_banques([awb, bmce], J30)

    _j28, j29, j30 = table.jours
    assert j29.ligne.cellules == (Cellule(1, D("110"), J28, True), Cellule(2, D("220"), J28, True))
    assert j30.ligne.cellules == (Cellule(1, D("130"), J30, False), Cellule(2, D("220"), J28, True))
    assert j30.ligne.total == D("350")
    assert j30.ligne.depassement == D("50")


def test_bank_before_its_first_balance_is_left_out_of_both_totals():
    awb = colonne(1, "100", [(J28, "10")])
    bmce = colonne(2, "200", [(J29, "20")])

    j28, j29 = tableau_banques([awb, bmce], J29).jours

    assert j28.ligne.cellules[1] == Cellule(2, None, None, False)
    assert j28.ligne.total == D("110")
    assert j28.ligne.depassement == D("10")  # 110 − 100 : la LIGNE de BMCE n'est pas comptée
    assert j29.ligne.total == D("330")


def test_every_calendar_day_has_a_row_weekends_included():
    awb = colonne(1, "0", [(J26, "1"), (J29, "4")])  # vendredi puis lundi

    table = tableau_banques([awb], J29)

    assert [jour.date for jour in table.jours] == [J26, J27, J28, J29]


def test_balances_after_the_end_date_are_ignored():
    awb = colonne(1, "0", [(J29, "1"), (date(2025, 10, 1), "999")])

    table = tableau_banques([awb], J30)

    assert [jour.date for jour in table.jours] == [J29, J30]
    assert table.disponible.cellules[0] == Cellule(1, D("1"), J29, True)


def test_bank_without_account_has_empty_cells_and_no_ligne():
    awb = colonne(1, "100", [(J30, "1")])
    bp = colonne(3, compte=False)

    table = tableau_banques([awb, bp], J30)

    assert table.jours[0].ligne.cellules[1] == Cellule(3, None, None, False)
    assert table.ligne_total == D("100")


def test_no_balance_at_all_gives_no_day_and_unknown_disponible():
    table = tableau_banques([colonne(1, "100"), colonne(2, compte=False)], J30)

    assert table.jours == ()
    assert table.disponible.total is None
    assert table.disponible.depassement is None
    assert [cellule.valeur for cellule in table.disponible.cellules] == [None, None]
    assert table.ligne_total == D("100")


def test_no_account_at_all_gives_no_ligne_total():
    assert tableau_banques([colonne(1, compte=False)], J30).ligne_total is None


def test_long_history_has_one_row_per_calendar_day():
    debut = date(2024, 9, 1)
    awb = colonne(1, "0", [(debut, "5")])

    table = tableau_banques([awb], debut + timedelta(days=399))

    assert len(table.jours) == 400
    assert table.jours[-1].ligne.cellules[0].reprise is True


def test_table_amounts_are_decimals():
    table = tableau_banques([colonne(1, "500000.50", [(J30, "0.25")])], J30)

    line = table.jours[0].ligne
    assert isinstance(line.cellules[0].valeur, Decimal)
    assert isinstance(line.total, Decimal)
    assert line.cellules[0].valeur == D("500000.75")


# --- Tableau Devises : soldes des comptes EUR / USD (décision du 05/10/2026) ---------------------


def test_devise_line_takes_each_bank_balance_in_its_currency():
    """Pas de conversion : TOTAL = somme des soldes de la même devise."""
    line = ligne_devise("EUR", [1, 3, 4], {1: [(J30, D("1500.50"))], 4: [(J29, D("200"))]}, J30)

    assert line.devise == "EUR"
    assert line.cellules == (
        Cellule(1, D("1500.50"), J30, False),
        Cellule(3, None, None, False),  # pas de compte EUR à cette banque
        Cellule(4, D("200"), J29, True),  # dernier solde connu, repris
    )
    assert line.total == D("1700.50")


def test_devise_line_ignores_balances_after_the_end_date_and_before_2000():
    line = ligne_devise(
        "USD",
        [1],
        {1: [(date(1999, 12, 31), D("9")), (J28, D("1")), (date(2025, 10, 1), D("999"))]},
        J30,
    )

    assert line.cellules == (Cellule(1, D("1"), J28, True),)
    assert line.total == D("1")


def test_devise_line_without_any_balance_has_no_total():
    line = ligne_devise("USD", [1, 2], {1: []}, J30)

    assert [cellule.valeur for cellule in line.cellules] == [None, None]
    assert line.total is None
