"""Règles pures du rapprochement 1→1 (P11) : score d'une paire et choix des propositions."""

from datetime import date, timedelta
from decimal import Decimal

from app.services.reconciliation_scoring import (
    GRILLE_PAR_DEFAUT,
    Ecriture,
    Grille,
    Operation,
    _peut_atteindre,
    comparable,
    ecart_jours,
    numeros,
    proposer,
    proposer_elargi,
    ratio_date,
    score,
    type_ecriture,
    type_operation,
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


# Libellés par défaut : un chèque des deux côtés (28/10/2026 : espèces, virement et autre ont leur
# propre grille, sans référence et +10 par critère, testée à part)
CHQ_OP = "ENCAISSEMENT CHEQUE ABC"
CHQ_EC = "EAR1° ENCAISSEMENT CHEQUE ABC"


def op(id=1, montant="50000", jour=JOUR, libelle=CHQ_OP, reference=None, valeur=None):
    return Operation(
        id=id,
        date_operation=jour,
        date_valeur=valeur,
        libelle=libelle,
        reference=reference,
        montant=Decimal(montant),
    )


def ec(id=1, montant="-50000", jour=JOUR, libelle=CHQ_EC, piece="REG458", **over):
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
        "montant": Decimal("40.00"),  # montant rond (28/10/2026)
        "date": Decimal("30.00"),
        "libelle": Decimal("20.00"),
        "tiers": Decimal("0.00"),
    }
    assert resultat.total == Decimal("90.00")


def test_the_score_uses_cheque_number_amount_date_and_label():
    """Décisions du 07 et du 08/10/2026 : tiers désactivé, n° de chèque / référence réactivé."""
    grille = Grille()
    resultat = score(op(libelle="ENCAISSEMENT CHEQUE REG458 ABC"), ec())

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
    resultat = score(op(libelle="ENCAISSEMENT CHEQUE REG-458 ABC"), ec(), AVEC_REFERENCE)

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
    bp = Ecriture(1, JOUR, "Virement ABC", None, None, "ABC", Decimal("-100"), bank_account_id=2)

    assert not comparable(awb, bp, Grille())
    assert proposer([awb], [bp]).propositions == []


def test_a_bank_credit_matches_a_sage_debit_only():
    assert comparable(op(montant="100"), ec(montant="-100"), Grille())
    assert not comparable(op(montant="100"), ec(montant="100"), Grille())
    assert not comparable(op(montant="-100"), ec(montant="-100"), Grille())
    assert proposer([op(montant="100")], [ec(montant="100")]).propositions == []


def test_amount_points_need_the_exact_amount():
    assert score(op(montant="12500"), ec(montant="-12450")).detail["montant"] == Decimal("0.00")
    assert score(op(montant="-12500"), ec(montant="12500")).detail["montant"] == Decimal("40.00")


def test_an_amount_with_cents_is_worth_more_than_a_round_one():
    """28/10/2026 : 60 points avec centimes, 40 sans ; le total reste plafonné à 100."""
    centimes = score(op(montant="12500.50"), ec(montant="-12500.50"))
    assert centimes.detail["montant"] == Decimal("60.00")
    assert centimes.total == Decimal("100.00")
    assert score(op(montant="-0.05"), ec(montant="0.05")).detail["montant"] == Decimal("60.00")
    assert score(op(montant="12500.00"), ec(montant="-12500.00")).detail["montant"] == (
        Decimal("40.00")
    )
    reglee = Grille(montant=Decimal("70"), montant_rond=Decimal("30"))
    assert score(op(montant="10.10"), ec(montant="-10.10"), reglee).detail["montant"] == (
        Decimal("70.00")
    )
    assert score(op(montant="10"), ec(montant="-10"), reglee).detail["montant"] == Decimal("30.00")


def test_date_points_decrease_until_the_tolerance():
    points = [score(op(jour=date(2026, 9, 24 + ecart)), ec()).detail["date"] for ecart in range(5)]

    assert points == [Decimal(v) for v in ("30.00", "22.50", "15.00", "7.50", "0.00")]
    assert ratio_date(0, 0) == 1 and ratio_date(1, 0) == 0


def test_value_date_counts_only_for_especes_and_virements():
    """12/10/2026 : la date de valeur sert aux espèces et aux virements ; chèques et effets prennent
    la date d'opération (la banque décale la date de valeur)."""
    banque = op(jour=date(2026, 9, 28), valeur=JOUR)

    assert score(banque, ec(libelle="Virement ATLAS")).detail["date"] == Decimal("30.00")
    assert score(banque, ec(libelle="EAR° 3308407 LAHNINE")).detail["date"] == Decimal("0.00")
    assert score(banque, ec(libelle="EAR1° AXK 173813")).detail["date"] == Decimal("0.00")


def test_effets_and_cheques_use_the_entry_date_not_the_due_date():
    """12/10/2026 : chèques et effets se comparent à la date de l'écriture, même avec une échéance."""
    effet = ec(libelle="EAR° 3308407 LAHNINE", jour=date(2026, 8, 1), echeance=JOUR)
    cheque = ec(libelle="EAR1° AXK 173813", jour=date(2026, 8, 1), echeance=JOUR)

    assert not comparable(op(), effet, GRILLE_PAR_DEFAUT)  # date de l'écriture hors fenêtre
    assert not comparable(op(), cheque, GRILLE_PAR_DEFAUT)
    assert score(op(jour=date(2026, 9, 25)), ec(libelle="EAR° 3308407")).detail["date"] == (
        Decimal("22.50")
    )


def test_virements_are_typed_and_compared_at_their_due_date():
    assert type_ecriture("Virement ATLAS TEXTILE") == "Virement"
    assert type_operation("VIR CLIENT ATLAS TEXTILE") == "Virement"
    assert type_operation("VIREMENT SALAIRES") == "Virement"
    assert type_operation("RTGS EMIS VERS CIH") == "Virement"
    virement = ec(libelle="Virement ATLAS", jour=date(2026, 8, 1), echeance=JOUR)

    # 28/10/2026 : un virement n'a pas de points de référence, 10 de plus par critère (date 40)
    assert score(op(libelle="VIR ATLAS"), virement).detail["date"] == Decimal("40.00")
    # Un virement ne se rapproche jamais d'un chèque
    assert not comparable(op(libelle="VIR ATLAS"), ec(libelle="EAR1° 1234567"), GRILLE_PAR_DEFAUT)


def test_entries_outside_the_window_are_not_compared():
    assert comparable(op(jour=date(2026, 10, 4)), ec(), Grille())
    assert not comparable(op(jour=date(2026, 10, 5)), ec(), Grille())


def test_unrelated_labels_score_low():
    resultat = score(op(libelle="PRLV ONEE"), ec(libelle="Achat fournitures", tiers=None))

    # Deux types inconnus (autre) : libellé sur 30 points (28/10/2026), moins d'un quart ici
    assert resultat.detail["libelle"] < Decimal("7.5")
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
    sans_montant = Grille(montant=Decimal("0"), montant_rond=Decimal("0"))
    assert score(op(), ec(), sans_montant).total == Decimal("50.00")
    assert sans_montant.criteres_actifs == ("reference", "date", "libelle")
    assert Grille(montant=Decimal("0")).criteres_actifs[1] == "montant"


def test_a_close_but_lower_candidate_no_longer_blocks_the_best():
    """Décision du 08/10/2026 : seule une égalité rend ambigu ; le suivant est gardé dans `second`."""
    meme_jour = ec(id=1)
    lendemain = ec(id=2, jour=date(2026, 9, 25))

    resultat = proposer([op()], [meme_jour, lendemain])

    [proposition] = resultat.propositions
    assert (proposition.ecriture_id, proposition.score.total) == (1, Decimal("90.00"))
    assert proposition.second == Decimal("82.50")
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
    banque = op(libelle="ENCAISSEMENT CHEQUE N 0173813 TIRE SUR ATW")

    meme = score(banque, ec(libelle="EAR1° AXK 173813 JAID MOHAMED ADNAN", piece=None))
    autre = score(banque, ec(libelle="EAR1° AXK 173814 JAID MOHAMED ADNAN", piece=None))
    remise = score(
        op(libelle="REMISE D'EFFETS N 5812970 A L'ESCOMPTE/N°3308407"),
        ec(libelle="EAR° 3308407 LAHNINE", piece=None),
    )

    assert meme.detail["reference"] == Decimal("40.00")
    assert autre.detail["reference"] == Decimal("0.00")
    assert remise.detail["reference"] == Decimal("40.00")


def test_the_right_cheque_wins_even_four_days_apart():
    """Cas réel du 28/08/2026 : le bon chèque passé 4 jours plus tôt en banque, un autre le jour même."""
    entry = ec(
        id=1, montant="-60000", jour=date(2026, 8, 28), piece=None,
        libelle="EAR1° AXK 173813 JAID", tiers=None,
    )  # fmt: skip
    bon = op(
        id=1, montant="60000", jour=date(2026, 8, 24),
        libelle="ENCAISSEMENT CHEQUE N 0173813 TIRE SUR ATW",
    )  # fmt: skip
    voisin = op(
        id=2, montant="60000", jour=date(2026, 8, 28),
        libelle="ENCAISSEMENT CHEQUE N 0173814 TIRE SUR ATW",
    )  # fmt: skip

    resultat = proposer([bon, voisin], [entry])

    [proposition] = resultat.propositions
    assert proposition.operation_id == 1
    assert score(bon, entry).detail["date"] == Decimal("0.00")


# --- Pré-filtre du moteur (08/10/2026) : il ne change jamais le résultat ---------------------------


def test_a_different_amount_is_never_proposed_even_at_the_threshold():
    """Montant différent, même jour, même libellé : 30 + 20 = 50, juste au seuil ; depuis le
    28/10/2026, jamais proposé ni ambigu (le score reste affiché à titre indicatif)."""
    banque = op(montant="50000", libelle="ENCAISSEMENT CHEQUE ATLAS SARL")
    entry = ec(
        montant="-49000", libelle="EAR1° ENCAISSEMENT CHEQUE ATLAS SARL", piece=None, tiers=None
    )
    meme_montant = ec(
        id=2, montant="-50000", jour=JOUR + timedelta(days=3), piece=None, tiers=None,
        libelle="EAR1° AUTRE CLIENT",
    )  # fmt: skip

    assert score(banque, entry).total == Decimal("50.00")
    assert _peut_atteindre(banque, entry, GRILLE_PAR_DEFAUT)
    assert proposer([banque], [entry]).propositions == []
    assert proposer([banque], [entry]).operations_ambigues == set()
    # Seule la candidate au même montant compte, même avec un score plus bas
    [proposition] = proposer([banque], [entry, meme_montant]).propositions
    assert proposition.ecriture_id == 2


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
           libelle=f"Virement client {i % 5} cheque N 0{100000 + i % 9}", piece=None)
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


# --- Type d'opération (09/10/2026) ---------------------------------------------------------------


def test_types_are_read_from_the_labels_of_each_side():
    assert type_ecriture("EAR1° AXK 173813 JAID") == "Chèque"
    assert type_ecriture("EAR° 3308407 LAHNINE") == "Effet"
    assert type_ecriture("ESP N 1234") == "Espèces"
    assert type_ecriture("REGLEMENT FOURNISSEUR ATLAS") is None
    # « LCN … » côté Sage : un effet (28/10/2026) ; « IMP LCN … » reste un impayé
    assert type_ecriture("LCN 2600083 TIRE SUR BP") == "Effet"
    assert type_ecriture("IMP LCN 2600083") == "Impayé"
    assert type_operation("ENCAISSEMENT CHEQUE N 0173813 TIRE SUR ATW") == "Chèque"
    assert type_operation("ENCAISSEMENT EFFET N 3100821") == "Effet"
    assert type_operation("REMISE D'EFFETS N 5812970") == "Effet"
    assert type_operation("VERSEMENT DEPLACE PAR UN TIERS") == "Espèces"
    assert type_operation("FRAIS RECUPERES PAR LA BANQUE") is None


def test_different_types_are_never_compared():
    cheque = op(libelle="ENCAISSEMENT CHEQUE N 0173813")
    especes = op(libelle="VERSEMENT DEPLACE PAR UN TIERS")
    autre = op(libelle="FRAIS RECUPERES PAR LA BANQUE")
    ecriture_cheque = ec(libelle="EAR1° AXK 173813")

    ecriture_autre = ec(libelle="REGLEMENT FOURNISSEUR ATLAS")

    assert comparable(cheque, ecriture_cheque, GRILLE_PAR_DEFAUT)
    assert not comparable(especes, ecriture_cheque, GRILLE_PAR_DEFAUT)
    # 28/10/2026 : un type inconnu (autre) ne se compare qu'à un autre type inconnu
    assert not comparable(autre, ecriture_cheque, GRILLE_PAR_DEFAUT)
    assert not comparable(cheque, ecriture_autre, GRILLE_PAR_DEFAUT)
    assert comparable(autre, ecriture_autre, GRILLE_PAR_DEFAUT)
    assert proposer([especes], [ecriture_cheque]).propositions == []
    assert proposer([autre], [ecriture_cheque]).propositions == []


def test_especes_are_compared_at_their_due_date():
    """12/10/2026 : les espèces se rapprochent par l'échéance Sage, comme les effets."""
    versement = op(montant="4000", libelle="VERSEMENT DEPLACE PAR UN TIERS")
    especes = ec(montant="-4000", jour=date(2026, 8, 1), echeance=JOUR, libelle="ESP TT23241QZKZC")
    cheque = ec(montant="-4000", jour=date(2026, 8, 1), echeance=JOUR, libelle="EAR1° 1234567")

    assert score(versement, especes).detail["date"] == Decimal("40.00")  # +10 (28/10/2026)
    assert proposer([versement], [especes]).propositions
    assert ecart_jours(op(libelle="ENCAISSEMENT CHEQUE N 1234567"), cheque) == 54


# --- Même n° et même montant : comparé jusqu'à 180 jours (12/10/2026) ------------------------------


def test_an_effet_with_the_same_number_and_amount_is_proposed_far_in_date():
    banque = op(montant="20000", jour=JOUR, libelle="ENCAISSEMENT EFFET N 0555848 TIRE SUR ATW")
    loin = ec(montant="-20000", jour=date(2026, 7, 26), libelle="EAR° ABN 555848 MR EL BAKOURI")

    [proposition] = proposer([banque], [loin]).propositions

    assert proposition.score.total >= Grille().seuil_fort  # montant 50 + n° 40, sans la date
    assert proposition.score.detail["date"] == Decimal("0.00")


def test_far_in_date_needs_the_same_number_and_the_same_amount():
    banque = op(montant="20000", libelle="ENCAISSEMENT CHEQUE N 1550018 EMIS PAR MR X")
    autre_montant = ec(montant="-19000", jour=date(2026, 7, 26), libelle="EAR1° 1550018 X")
    autre_numero = ec(montant="-20000", jour=date(2026, 7, 26), libelle="EAR1° 1550019 X")
    trop_loin = ec(montant="-20000", jour=date(2026, 1, 2), libelle="EAR1° 1550018 X")

    for ecriture in (autre_montant, autre_numero, trop_loin):
        assert not comparable(banque, ecriture, GRILLE_PAR_DEFAUT)
    assert proposer([banque], [autre_montant, autre_numero, trop_loin]).propositions == []


def test_an_unpaid_is_matched_by_its_number_far_in_date():
    """16/10/2026 : l'impayé de la banque et l'« IMP EAR° » de Sage se rapprochent par leur n°,
    jusqu'à 180 jours, et jamais avec un encaissement."""
    impaye = op(montant="-25000", jour=JOUR, libelle="IMPAYE SUR EFFET ESCOMPTE N 2600009 TIRE")
    sage = ec(
        id=10, montant="25000", jour=JOUR - timedelta(days=40), libelle="IMP EAR° ABC 2600009 X"
    )
    encaissement = ec(id=11, montant="25000", jour=JOUR, libelle="EAR° ABC 2600009 X")

    assert type_operation(impaye.libelle) == type_ecriture(sage.libelle) == "Impayé"
    assert type_ecriture("IMP EAR1° AXL 917714 AJETTAR") == "Impayé"
    assert type_operation("IMPOTS ET TAXES") is None
    assert not comparable(impaye, encaissement, GRILLE_PAR_DEFAUT)
    [proposition] = proposer([impaye], [sage, encaissement]).propositions
    assert proposition.ecriture_id == sage.id
    assert proposition.score.total >= Grille().seuil_fort


def test_without_a_number_the_window_stays_10_days():
    banque = op(montant="4000", libelle="VERSEMENT DEPLACE PAR UN TIERS")
    especes = ec(montant="-4000", jour=date(2026, 8, 1), libelle="ESP TT23241QZKZC")

    assert not comparable(banque, especes, GRILLE_PAR_DEFAUT)


# --- Ambiguïté seulement en cas d'égalité (16/10/2026) ---------------------------------------------


def test_a_line_taken_by_a_better_pair_gives_way_to_the_next_candidate():
    """B préfère l'écriture E1 (1 jour d'écart), mais E1 préfère A (même jour) : A prend E1, puis
    B reçoit sa candidate suivante E2 (2 jours d'écart), sans ambiguïté."""
    a = op(id=1, jour=JOUR)
    b = op(id=2, jour=JOUR + timedelta(days=1))
    meme_jour = ec(id=10, jour=JOUR)
    lendemain = ec(id=11, jour=JOUR + timedelta(days=3))

    resultat = proposer([a, b], [meme_jour, lendemain])

    assert {(p.operation_id, p.ecriture_id) for p in resultat.propositions} == {(1, 10), (2, 11)}
    assert resultat.operations_ambigues == set() and resultat.ecritures_ambigues == set()


def test_two_identical_operations_facing_two_identical_entries_are_all_ambiguous():
    resultat = proposer([op(id=1), op(id=2)], [ec(id=10), ec(id=11)])

    assert resultat.propositions == []
    assert resultat.operations_ambigues == {1, 2}
    assert resultat.ecritures_ambigues == {10, 11}


# --- Recherche élargie (20/10/2026) ---------------------------------------------------------------


def test_a_far_pair_with_the_same_number_and_amount_is_found():
    banque = op(id=1, montant="20000", libelle="ENCAISSEMENT CHEQUE N 0174512 TIRE SUR ATW")
    loin = ec(id=10, montant="-20000", jour=JOUR - timedelta(days=200), libelle="EAR1° 174512 X")

    [proposition] = proposer_elargi([banque], [loin])

    assert (proposition.operation_id, proposition.ecriture_id) == (1, 10)
    assert proposition.ecart_jours == 200
    assert proposition.score.total >= Decimal("80")


def test_the_wide_search_needs_a_number_one_candidate_and_the_window():
    banque = op(id=1, montant="20000", libelle="ENCAISSEMENT CHEQUE N 0174512 TIRE SUR ATW")
    sans_numero = op(id=2, montant="700", libelle="VIR ABC")
    autre_montant = ec(
        id=10, montant="-19000", jour=JOUR - timedelta(days=50), libelle="EAR1° 174512"
    )
    trop_loin = ec(id=11, montant="-20000", jour=JOUR - timedelta(days=400), libelle="EAR1° 174512")
    # Virement sans n° (28/10/2026) : cherché par le libellé, ici trop différent
    vir = ec(id=12, montant="-700", jour=JOUR - timedelta(days=50), libelle="Virement XYZ AUTRE")

    assert proposer_elargi([banque, sans_numero], [autre_montant, trop_loin, vir]) == []
    # Deux écritures possibles pour la même opération : rien n'est choisi au hasard
    double = [
        ec(id=20, montant="-20000", jour=JOUR - timedelta(days=60), libelle="EAR1° 174512 A"),
        ec(id=21, montant="-20000", jour=JOUR - timedelta(days=90), libelle="EAR1° 174512 B"),
    ]
    assert proposer_elargi([banque], double) == []
    assert proposer_elargi([banque], [double[0]], paires_rejetees={(1, 20)}) == []


# --- Espèces : date pleine à ± 2 jours de l'échéance Sage, puis dégressive (28/10/2026) ---------


def especes_a(ecart_jours_echeance: int, libelle: str = "ESP TT26273B6Z6S") -> Ecriture:
    return ec(
        montant="-5000",
        jour=JOUR,
        echeance=JOUR + timedelta(days=ecart_jours_echeance),
        libelle=libelle,
    )


VERSEMENT = op(montant="5000", libelle="VERSEMENT DEPLACE PAR UN TIERS")


def test_cash_date_points_are_full_up_to_two_days_then_decrease():
    points = [score(VERSEMENT, especes_a(ecart)).detail["date"] for ecart in range(8)]

    assert points == [
        Decimal(v) for v in ("40.00", "40.00", "40.00", "30.00", "20.00", "10.00", "0.00", "0.00")
    ]
    # Plus de coupure à 2 jours : comparées jusqu'à la fenêtre de 10 jours, comme les autres
    assert comparable(VERSEMENT, especes_a(3), GRILLE_PAR_DEFAUT)
    assert comparable(VERSEMENT, especes_a(10), GRILLE_PAR_DEFAUT)
    assert not comparable(VERSEMENT, especes_a(11), GRILLE_PAR_DEFAUT)
    assert proposer([VERSEMENT], [especes_a(-3)]).propositions


def test_cash_full_date_applies_when_only_the_sage_side_is_known():
    """Un versement BP au libellé collé (type non reconnu) face à une écriture « ESP »."""
    colle = op(montant="5000", libelle="VERSEMENTDEPLACEPARIMANEELBAZCD760324")

    assert type_operation(colle.libelle) is None
    assert score(colle, especes_a(2, "ESP TT26251KM24D")).detail["date"] == Decimal("30.00")


def test_other_types_lose_date_points_from_the_first_day():
    cheque = op(montant="5000", libelle="ENCAISSEMENT CHEQUE N 1234567")
    ecriture = ec(montant="-5000", jour=JOUR + timedelta(days=2), libelle="EAR1° AXK 1234567")

    assert score(cheque, ecriture).detail["date"] == Decimal("15.00")


def test_the_cash_full_date_days_follow_the_setting():
    assert score(VERSEMENT, especes_a(4), Grille(fenetre_especes_jours=4)).detail["date"] == (
        Decimal("40.00")
    )
    assert score(VERSEMENT, especes_a(1), Grille(fenetre_especes_jours=0)).detail["date"] == (
        Decimal("30.00")
    )


def test_the_wide_search_finds_cash_by_amount_and_label():
    """28/10/2026 : espèces, virement et autre sont cherchés par le montant et un libellé semblable
    à 70 % au moins, sans n° commun."""
    versement = op(montant="5000", libelle="VERSEMENT DEPLACE PAR ALAMI")
    proche = ec(
        id=10, montant="-5000", jour=JOUR - timedelta(days=40),
        libelle="ESP VERSEMENT DEPLACE PAR ALAMI", piece=None,
    )  # fmt: skip
    eloigne = ec(
        id=11, montant="-5000", jour=JOUR - timedelta(days=40), libelle="ESP TT26273B6Z6S",
        piece=None,
    )  # fmt: skip

    assert [p.ecart_jours for p in proposer_elargi([versement], [proche])] == [40]
    assert proposer_elargi([versement], [eloigne]) == []


def test_cash_transfer_and_other_have_no_reference_points_and_ten_more_per_criterion():
    """28/10/2026 : espèces, virement et autre (même type des deux côtés) : référence 0, montant
    70 / 50, date 40, libellé 30 ; chèque, effet et impayé gardent la grille."""
    virement = score(
        op(montant="1250.50", libelle="VIR RECU ATLAS 1234567"),
        ec(montant="-1250.50", libelle="VIR ATLAS 1234567", piece=None),
    )
    autre = score(
        op(montant="300", libelle="OPERATION BANCAIRE X"),
        ec(montant="-300", libelle="REGULARISATION X", piece=None),
    )
    cheque = score(op(libelle="ENCAISSEMENT CHEQUE N 1234567"), ec(libelle="EAR1° 1234567"))

    assert virement.detail["reference"] == Decimal("0.00")  # n° commun, mais pas compté
    assert (virement.detail["montant"], virement.detail["date"]) == (
        Decimal("70.00"),
        Decimal("40.00"),
    )
    assert autre.detail["montant"] == Decimal("50.00")
    assert score(VERSEMENT, especes_a(0)).detail["montant"] == Decimal("50.00")
    assert cheque.detail["reference"] == Decimal("40.00")
    assert (cheque.detail["montant"], cheque.detail["date"]) == (Decimal("40.00"), Decimal("30.00"))
    sans_bonus = Grille(bonus_sans_reference=Decimal("0"))
    assert score(VERSEMENT, especes_a(0), sans_bonus).detail["montant"] == Decimal("40.00")


def test_the_engine_gives_the_same_score_as_score_for_cash_and_transfers():
    """28/10/2026 : le pré-filtre du moteur et `score` appliquent le bonus une seule fois."""
    virement = op(montant="1250", libelle="VIR RECU ATLAS")
    entree = ec(montant="-1250", libelle="VIR ATLAS", piece=None)

    [proposition] = proposer([virement], [entree]).propositions

    assert proposition.score == score(virement, entree)
    assert proposition.score.detail["montant"] == Decimal("50.00")
