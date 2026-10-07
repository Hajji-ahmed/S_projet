"""Règles pures du rapprochement 1→1 (P11) : score d'une paire et choix des propositions."""

from datetime import date
from decimal import Decimal

from app.services.reconciliation_scoring import (
    Ecriture,
    Grille,
    Operation,
    comparable,
    proposer,
    ratio_date,
    score,
)

JOUR = date(2026, 9, 24)
# Grille d'avant le 07/10/2026 : la règle Référence reste testée, prête à être réactivée
AVEC_REFERENCE = Grille(
    reference=Decimal("40"),
    montant=Decimal("30"),
    date=Decimal("15"),
    libelle=Decimal("10"),
    tiers=Decimal("5"),
)


def op(id=1, montant="50000", jour=JOUR, libelle="VIR ABC", reference=None, valeur=None):
    return Operation(
        id=id,
        date_operation=jour,
        date_valeur=valeur,
        libelle=libelle,
        reference=reference,
        montant=Decimal(montant),
    )


def ec(id=1, montant="-50000", jour=JOUR, libelle="Règlement ABC", piece="REG458", **over):
    return Ecriture(
        **{
            "id": id,
            "date_ecriture": jour,
            "libelle": libelle,
            "reference": None,
            "numero_piece": piece,
            "tiers": "ABC",
            "montant": Decimal(montant),
            **over,
        }
    )


def test_example_of_the_functional_architecture_scores_each_criterion():
    # Banque 50 000 le 24/09 « VIR ABC » ↔ compta 50 000 le 24/09 « Règlement ABC », pièce REG458
    resultat = score(op(), ec())

    assert resultat.detail == {
        "reference": Decimal("0.00"),
        "montant": Decimal("50.00"),
        "date": Decimal("30.00"),
        "libelle": Decimal("20.00"),
        "tiers": Decimal("0.00"),
    }
    assert resultat.total == Decimal("100.00")


def test_the_score_only_uses_amount_date_and_label_for_now():
    """Décision du 07/10/2026 : référence et tiers désactivés, même quand ils correspondent."""
    grille = Grille()
    resultat = score(op(libelle="VIR REG458 ABC"), ec())

    assert grille.criteres_actifs == ("montant", "date", "libelle")
    assert (resultat.detail["reference"], resultat.detail["tiers"]) == (Decimal("0.00"),) * 2


def test_example_is_proposed_as_a_strong_match():
    resultat = proposer([op()], [ec()])

    assert [(p.operation_id, p.ecriture_id) for p in resultat.propositions] == [(1, 1)]
    assert resultat.propositions[0].score.total >= Grille().seuil_fort


def test_piece_number_written_in_the_bank_label_gives_the_reference_points():
    resultat = score(op(libelle="VIR REG-458 ABC"), ec(), AVEC_REFERENCE)

    assert resultat.detail["reference"] == Decimal("40.00")
    assert resultat.total == Decimal("100.00")


def test_same_reference_on_both_sides_gives_the_reference_points():
    def points(reference, cle):
        resultat = score(op(reference=reference), ec(reference=cle, piece=None), AVEC_REFERENCE)
        return resultat.detail["reference"]

    assert points("1234567", "1234567") == Decimal("40.00")
    assert points("CHQ 1234567", "1234567") == Decimal("40.00")
    assert points("CHQ 1234567", "12345") == Decimal("0.00")
    assert points("CHQ 1234567", "67") == Decimal("0.00")


def test_an_entry_of_another_bank_account_is_not_compared():
    awb = Operation(1, JOUR, None, "VIR ABC", None, Decimal("100"), bank_account_id=1)
    bp = Ecriture(1, JOUR, "Règlement ABC", None, None, "ABC", Decimal("-100"), bank_account_id=2)

    assert not comparable(awb, bp, Grille())
    assert proposer([awb], [bp]).propositions == []


def test_a_bank_credit_matches_a_sage_debit_only():
    assert comparable(op(montant="100"), ec(montant="-100"), Grille())
    assert not comparable(op(montant="100"), ec(montant="100"), Grille())
    assert not comparable(op(montant="-100"), ec(montant="-100"), Grille())
    assert proposer([op(montant="100")], [ec(montant="100")]).propositions == []


def test_amount_points_need_the_exact_amount():
    assert score(op(montant="12500"), ec(montant="-12450")).detail["montant"] == Decimal("0.00")
    assert score(op(montant="-12500"), ec(montant="12500")).detail["montant"] == Decimal("50.00")


def test_date_points_decrease_until_the_tolerance():
    points = [score(op(jour=date(2026, 9, 24 + ecart)), ec()).detail["date"] for ecart in range(5)]

    assert points == [Decimal(v) for v in ("30.00", "22.50", "15.00", "7.50", "0.00")]
    assert ratio_date(0, 0) == 1 and ratio_date(1, 0) == 0


def test_value_date_is_used_when_closer():
    resultat = score(op(jour=date(2026, 9, 28), valeur=JOUR), ec())

    assert resultat.detail["date"] == Decimal("30.00")


def test_entries_outside_the_window_are_not_compared():
    assert comparable(op(jour=date(2026, 10, 4)), ec(), Grille())
    assert not comparable(op(jour=date(2026, 10, 5)), ec(), Grille())


def test_unrelated_labels_score_low():
    resultat = score(op(libelle="PRLV ONEE"), ec(libelle="Achat fournitures", tiers=None))

    assert resultat.detail["libelle"] < Decimal("5")
    assert resultat.detail["tiers"] == Decimal("0.00")


def test_below_the_threshold_nothing_is_proposed_nor_ambiguous():
    resultat = proposer(
        [op(libelle="PRLV ONEE")],
        [ec(montant="-49000", libelle="Achat", tiers=None, piece=None, jour=date(2026, 9, 30))],
    )

    assert resultat.propositions == []
    assert resultat.operations_ambigues == set()


def test_two_close_candidates_give_no_proposal():
    resultat = proposer([op()], [ec(id=1), ec(id=2)])

    assert resultat.propositions == []
    assert resultat.operations_ambigues == {1}
    assert resultat.ecritures_ambigues == {1, 2}


def test_one_entry_close_to_two_operations_is_not_proposed():
    resultat = proposer([op(id=1), op(id=2)], [ec()])

    assert resultat.propositions == []
    assert resultat.ecritures_ambigues == {1}


def test_a_clear_best_candidate_is_proposed():
    proche = ec(id=1)
    lointaine = ec(id=2, jour=date(2026, 9, 27), libelle="Autre libellé", tiers=None)

    resultat = proposer([op()], [proche, lointaine])

    assert [(p.operation_id, p.ecriture_id) for p in resultat.propositions] == [(1, 1)]
    assert resultat.operations_ambigues == set()


def test_each_entry_is_proposed_once_and_pairs_are_resolved_in_turn():
    a, b = op(id=1), op(id=2, jour=date(2026, 9, 26))
    first, second = ec(id=1), ec(id=2, jour=date(2026, 9, 26))

    resultat = proposer([a, b], [first, second])

    assert {(p.operation_id, p.ecriture_id) for p in resultat.propositions} == {(1, 1), (2, 2)}


def test_rejected_pairs_are_never_proposed_again():
    resultat = proposer([op()], [ec()], paires_rejetees={(1, 1)})

    assert resultat.propositions == []
    assert resultat.operations_ambigues == set()


def test_the_grid_is_configurable():
    assert proposer([op()], [ec()], Grille(seuil_proposition=Decimal("100.01"))).propositions == []
    assert score(op(), ec(), Grille(montant=Decimal("0"))).total == Decimal("50.00")
    assert Grille(montant=Decimal("0")).criteres_actifs == ("date", "libelle")
