"""Règles pures du rapprochement 1→1 (P11) : score d'une paire et choix des propositions."""

from datetime import date
from decimal import Decimal

from app.services.reconciliation_scoring import (
    GRILLE_PAR_DEFAUT,
    Ecriture,
    Grille,
    Operation,
    _peut_atteindre,
    comparable,
    numeros,
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


def test_the_score_uses_cheque_number_amount_date_and_label():
    """Décisions du 07 et du 08/10/2026 : tiers désactivé, n° de chèque / référence réactivé."""
    grille = Grille()
    resultat = score(op(libelle="VIR REG458 ABC"), ec())

    assert grille.criteres_actifs == ("reference", "montant", "date", "libelle")
    assert (resultat.detail["reference"], resultat.detail["tiers"]) == (
        Decimal("40.00"),
        Decimal("0.00"),
    )


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


def test_two_candidates_with_the_same_score_give_no_proposal():
    resultat = proposer([op()], [ec(id=1), ec(id=2)])

    assert resultat.propositions == []
    assert resultat.operations_ambigues == {1}
    assert resultat.ecritures_ambigues == {1, 2}


def test_one_entry_equal_for_two_operations_is_not_proposed():
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
    assert Grille(montant=Decimal("0")).criteres_actifs == ("reference", "date", "libelle")


def test_a_close_but_lower_candidate_no_longer_blocks_the_best():
    """Décision du 08/10/2026 : seule une égalité rend ambigu ; le suivant est gardé dans `second`."""
    meme_jour = ec(id=1)
    lendemain = ec(id=2, jour=date(2026, 9, 25))

    resultat = proposer([op()], [meme_jour, lendemain])

    [proposition] = resultat.propositions
    assert (proposition.ecriture_id, proposition.score.total) == (1, Decimal("100.00"))
    assert proposition.second == Decimal("92.50")
    assert resultat.operations_ambigues == set()


def test_a_single_candidate_has_no_second():
    [proposition] = proposer([op()], [ec()]).propositions

    assert proposition.second is None


def test_the_strong_threshold_is_80_by_default():
    assert GRILLE_PAR_DEFAUT.seuil_fort == Decimal("80")


# --- N° de chèque dans les libellés (08/10/2026) ---------------------------------------------------


def test_numbers_are_read_without_leading_zeros_and_short_ones_are_ignored():
    assert numeros("ENCAISSEMENT CHEQUE N 0173813 TIRE SUR ATW") == {"173813"}
    assert numeros("EAR1° AXV//574927 FATIMA") == {"574927"}
    assert numeros("REMISE D'EFFETS N 5812970 A L'ESCOMPTE/N°3308407") == {"5812970", "3308407"}
    assert numeros("EAR1° 1234 ABC", None) == set()


def test_same_cheque_number_in_both_labels_gives_the_reference_points():
    banque = op(libelle="EAR1° AXK 173813 JAID MOHAMED ADNAN")

    meme = score(banque, ec(libelle="ENCAISSEMENT CHEQUE N 0173813 TIRE SUR ATW", piece=None))
    autre = score(banque, ec(libelle="ENCAISSEMENT CHEQUE N 0173814 TIRE SUR ATW", piece=None))
    remise = score(
        op(libelle="EAR° 3308407 LAHNINE"),
        ec(libelle="REMISE D'EFFETS N 5812970 A L'ESCOMPTE/N°3308407", piece=None),
    )

    assert meme.detail["reference"] == Decimal("40.00")
    assert autre.detail["reference"] == Decimal("0.00")
    assert remise.detail["reference"] == Decimal("40.00")


def test_the_right_cheque_wins_even_four_days_apart():
    """Cas réel du 28/08/2026 : le bon chèque passé 4 jours plus tôt en banque, un autre le jour même."""
    entry = ec(
        id=1, montant="-60000", jour=date(2026, 8, 28), piece=None,
        libelle="ENCAISSEMENT CHEQUE N 0173813 TIRE SUR ATW", tiers=None,
    )  # fmt: skip
    bon = op(id=1, montant="60000", jour=date(2026, 8, 24), libelle="EAR1° AXK 173813 JAID")
    voisin = op(id=2, montant="60000", jour=date(2026, 8, 28), libelle="EAR1° AXK 173814 JAID")

    resultat = proposer([bon, voisin], [entry])

    [proposition] = resultat.propositions
    assert proposition.operation_id == 1
    assert score(bon, entry).detail["date"] == Decimal("0.00")


# --- Pré-filtre du moteur (08/10/2026) : il ne change jamais le résultat ---------------------------


def test_the_prefilter_never_drops_a_pair_that_reaches_the_threshold():
    """Montant différent, même jour, même libellé : 30 + 20 = 50, juste au seuil : candidat."""
    banque = op(montant="50000", libelle="VIR ATLAS SARL")
    entry = ec(montant="-49000", libelle="VIR ATLAS SARL", piece=None, tiers=None)

    assert score(banque, entry).total == Decimal("50.00")
    assert _peut_atteindre(banque, entry, GRILLE_PAR_DEFAUT)
    assert proposer([banque], [entry]).propositions != []


def test_the_prefilter_skips_pairs_that_cannot_reach_the_threshold():
    banque = op(montant="50000", libelle="VIR ATLAS SARL")
    lendemain = ec(montant="-49000", jour=date(2026, 9, 25), piece=None, tiers=None)
    meme_cheque = ec(
        montant="-49000", jour=date(2026, 9, 25), piece=None, tiers=None,
        libelle="CHEQUE N 0173813",
    )  # fmt: skip

    assert not _peut_atteindre(banque, lendemain, GRILLE_PAR_DEFAUT)
    assert _peut_atteindre(op(libelle="EAR1° AXK 173813"), meme_cheque, GRILLE_PAR_DEFAUT)


def test_the_prefilter_gives_the_same_result_as_scoring_every_pair():
    operations = [
        op(id=i, montant=str(1000 + (i % 7) * 10), jour=date(2026, 9, 1 + i % 20),
           libelle=f"VIR CLIENT {i % 5} CHQ {100000 + i % 9}")
        for i in range(1, 60)
    ]  # fmt: skip
    ecritures = [
        ec(id=i, montant=str(-(1000 + (i % 7) * 10)), jour=date(2026, 9, 1 + (i * 3) % 20),
           libelle=f"Règlement client {i % 5} cheque N 0{100000 + i % 9}", piece=None)
        for i in range(1, 60)
    ]  # fmt: skip
    attendus = {
        (o.id, e.id)
        for o in operations
        for e in ecritures
        if comparable(o, e, GRILLE_PAR_DEFAUT)
        and score(o, e).total >= GRILLE_PAR_DEFAUT.seuil_proposition
    }
    retenus = {
        (o.id, e.id)
        for o in operations
        for e in ecritures
        if comparable(o, e, GRILLE_PAR_DEFAUT) and _peut_atteindre(o, e, GRILLE_PAR_DEFAUT)
    }

    assert attendus <= retenus
