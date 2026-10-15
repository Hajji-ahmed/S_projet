"""Rapprochement groupé N → 1 (12/10/2026) : règles pures."""

from datetime import date
from decimal import Decimal

from app.services.reconciliation_groupes import famille_frais, grouper, operations_couvertes
from app.services.reconciliation_scoring import GRILLE_PAR_DEFAUT, Ecriture, Operation

JOUR = date(2026, 4, 21)


def op(id, montant, libelle, jour=JOUR, compte=1):
    return Operation(
        id=id,
        date_operation=jour,
        date_valeur=None,
        libelle=libelle,
        reference=None,
        montant=Decimal(montant),
        bank_account_id=compte,
    )


def ec(id, montant, libelle, jour=JOUR, compte=1, echeance=None):
    return Ecriture(
        id=id,
        date_ecriture=jour,
        libelle=libelle,
        reference=None,
        numero_piece=None,
        tiers=None,
        montant=Decimal(montant),
        bank_account_id=compte,
        echeance=echeance,
    )


def groupes(operations, ecritures, rejetees=frozenset()):
    return grouper(operations, ecritures, GRILLE_PAR_DEFAUT, rejetees)


def test_fee_families_are_read_from_the_label():
    assert famille_frais("DROITS DE TIMBRE SUR REMISE LCN N 7082678") == "timbre"
    assert famille_frais("TAXE SUR VALEUR AJOUTEE") == "tva"
    assert famille_frais("COMMISSION") == "commission"
    assert famille_frais("INTERET REMISE LCN A L'ESCOMPTE") == "interet"
    assert famille_frais("ENCAISSEMENT CHEQUE N 1550018") is None


def test_cheque_plus_commission_plus_tva_is_one_entry():
    """L'exemple de la demande : 10 000 + 50 + 10 = 10 060 (paiement : tout au débit)."""
    banque = [
        op(1, "-10000", "CHEQUE N 2100843 REMIS PAR ATW"),
        op(2, "-50", "COMMISSION"),
        op(3, "-10", "TAXE SUR VALEUR AJOUTEE"),
        op(4, "-20", "COMMISSION"),  # d'un autre groupe : écartée
    ]

    [groupe] = groupes(banque, [ec(9, "10060", "CHQ° 2100843 FOURNISSEUR")]).groupes

    assert groupe.operation_ids == (1, 2, 3)
    assert groupe.principale_id == 1
    assert groupe.score.detail["montant"] == Decimal("50.00")
    assert groupe.score.detail["reference"] == Decimal("40.00")
    assert "= 10 060,00" in groupe.explication
    assert "n° 2100843 commun" in groupe.explication


def test_effet_plus_stamp_by_reference():
    banque = [
        op(1, "648360", "REMISE D'EFFETS N 7082678 A L'ESCOMPTE"),
        op(2, "-195", "DROITS DE TIMBRE SUR REMISE LCN N 7082678"),
    ]

    [groupe] = groupes(banque, [ec(9, "-648165", "REMISE LCN 7082678")]).groupes

    assert groupe.operation_ids == (1, 2)


def test_virement_and_especes_plus_fees():
    virement = [op(1, "25000", "VIR. RECU DE MR X REF 9010021"), op(2, "-15", "FRAIS VIREMENT")]
    especes = [op(3, "4000", "VERSEMENT DEPLACE PAR UN TIERS"), op(4, "-1", "DROIT DE TIMBRE")]

    a = groupes(virement, [ec(8, "-24985", "VIR CLIENT X")]).groupes
    b = groupes(especes, [ec(9, "-3999", "ESP TT23241QZKZC")]).groupes

    assert [g.operation_ids for g in a] == [(1, 2)]
    assert [g.operation_ids for g in b] == [(3, 4)]


def test_day_fees_match_the_daily_entries():
    """Timbres du jour = DT D'ENREGISTREMENT ; intérêt + TVA = FRAIS D'ESCOMPTE (cas réels BP)."""
    banque = [
        op(1, "-20", "DROITS DE TIMBRE SUR REMISE LCN N 2102156"),
        op(2, "-200", "DROITS DE TIMBRE SUR REMISE LCN N 7082677"),
        op(3, "-195", "DROITS DE TIMBRE SUR REMISE LCN N 7082678"),
        op(4, "-4320.95", "INTERET REMISE LCN A L'ESCOMPTE"),
        op(5, "-432.09", "TAXE SUR VALEUR AJOUTEE"),
    ]
    ecritures = [ec(8, "415", "DT D'ENREGISTREMENT"), ec(9, "4753.04", "FRAIS D'ESCOMPTE/7082678")]

    resultat = groupes(banque, ecritures)

    assert {(g.ecriture_id, g.operation_ids) for g in resultat.groupes} == {
        (8, (1, 2, 3)),
        (9, (4, 5)),
    }


def test_a_wrong_sum_gives_no_group():
    banque = [op(1, "-10000", "CHEQUE N 2100843"), op(2, "-50", "COMMISSION")]

    assert groupes(banque, [ec(9, "10060", "CHQ° 2100843")]).groupes == []


def test_two_different_groups_make_the_entry_ambiguous():
    banque = [
        op(1, "-1000", "CHEQUE N 1111111"),
        op(2, "-1000", "PAIEMENT FOURNISSEUR"),
        op(3, "-50", "COMMISSION"),
    ]

    resultat = groupes(banque, [ec(9, "1050", "REGLEMENT")])

    assert resultat.groupes == []
    assert resultat.ecritures_ambigues == {9}


def test_identical_fee_lines_are_not_ambiguous():
    banque = [
        op(1, "-20", "COMMISSION"),
        op(2, "-2", "TAXE SUR VALEUR AJOUTEE"),
        op(3, "-20", "COMMISSION"),
        op(4, "-2", "TAXE SUR VALEUR AJOUTEE"),
    ]

    [groupe] = groupes(banque, [ec(9, "22", "COM")]).groupes

    assert len(groupe.operation_ids) == 2


def test_an_operation_joins_one_group_only_and_rejected_pairs_are_skipped():
    banque = [op(1, "-10000", "CHEQUE N 2100843"), op(2, "-60", "COMMISSION")]
    deux = [ec(8, "10060", "CHQ° 2100843 A"), ec(9, "10060", "CHQ° 2100843 B")]

    resultat = groupes(banque, deux)
    rejete = groupes(banque, [deux[0]], rejetees={(1, 8)})

    assert len(resultat.groupes) == 1
    assert rejete.groupes == []


def test_another_account_or_far_date_is_never_grouped():
    autre_compte = [op(1, "-10000", "CHEQUE N 2100843", compte=2), op(2, "-60", "COMMISSION")]
    loin = [
        op(3, "-10000", "CHEQUE N 2100843", jour=date(2026, 6, 1)),
        op(4, "-60", "COMMISSION", jour=date(2026, 6, 1)),
    ]

    assert groupes(autre_compte, [ec(9, "10060", "CHQ° 2100843")]).groupes == []
    assert groupes(loin, [ec(9, "10060", "CHQ° 2100843")]).groupes == []


# --- Opérations couvertes par une écriture Sage (13/10/2026) -------------------------------------


def test_a_principal_and_its_fees_are_covered_by_the_sage_entry():
    ops = [
        op(1, "-10000", "VIREMENT EMIS FOURNISSEUR X"),
        op(2, "-50", "COMMISSION"),
        op(3, "-5", "TAXE SUR VALEUR AJOUTEE"),
        op(4, "-1", "DROIT DE TIMBRE SUR VERSEMENT"),
    ]
    vir = ec(10, "10055", "VIR FOURNISSEUR X")
    # 1 + 50 + 5 = 56 : une « COM » ne contient jamais de droit de timbre
    com = ec(11, "56", "COM")

    assert operations_couvertes(ops, [vir, com], GRILLE_PAR_DEFAUT) == {1: 10, 2: 10, 3: 10}
    # Une paire rejetée par un utilisateur ne couvre plus rien
    assert operations_couvertes(ops, [vir], GRILLE_PAR_DEFAUT, {(2, 10)}) == {}


def test_a_fee_alone_is_covered_by_an_entry_of_the_opposite_amount_within_3_days():
    agios = op(1, "-30", "AGIOS BANCAIRES")

    assert operations_couvertes(
        [agios], [ec(10, "30", "AGIOS", jour=date(2026, 4, 23))], GRILLE_PAR_DEFAUT
    ) == {1: 10}
    assert (
        operations_couvertes(
            [agios], [ec(10, "30", "AGIOS", jour=date(2026, 4, 26))], GRILLE_PAR_DEFAUT
        )
        == {}
    )
