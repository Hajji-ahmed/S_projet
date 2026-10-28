"""Rapprochement groupé N → 1 (12/10/2026) : règles pures."""

from datetime import date
from decimal import Decimal

from app.services.reconciliation_groupes import (
    famille_frais,
    grouper,
    operations_couvertes,
    tva_de_la_commission,
)
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
    """10 000 + commission 50 + TVA 5 (10 %) = 10 055 (paiement : tout au débit)."""
    banque = [
        op(1, "-10000", "CHEQUE N 2100843 REMIS PAR ATW"),
        op(2, "-50", "COMMISSION"),
        op(3, "-5", "TAXE SUR VALEUR AJOUTEE"),
        op(4, "-20", "COMMISSION"),  # d'un autre groupe : écartée
    ]

    [groupe] = groupes(banque, [ec(9, "10055", "CHQ° 2100843 FOURNISSEUR")]).groupes

    assert groupe.operation_ids == (1, 2, 3)
    assert groupe.principale_id == 1
    assert groupe.score.detail["montant"] == Decimal("40.00")  # somme ronde (28/10/2026)
    assert groupe.score.detail["reference"] == Decimal("40.00")
    assert "= 10 055,00" in groupe.explication
    assert "n° 2100843 commun" in groupe.explication


def test_only_principal_plus_commission_plus_its_vat_is_grouped():
    """15/10/2026 : seul le trio principale + commission + TVA (10 %) est regroupé. Deux
    commissions sans TVA (le cas réel 12 450 − 175 − 25 = 12 250), une TVA qui n'est pas 10 %,
    un timbre au même n° ou des frais de virement ne forment plus de groupe."""
    deux_commissions = [
        op(1, "12450", "VIR. INSTANTANE RECU DE MR RABHI MOHAMED"),
        op(2, "-175", "COMMISSION"),
        op(3, "-25", "COMMISSION"),
    ]
    tva_fausse = [op(4, "-1000", "PAIEMENT X"), op(5, "-50", "COMMISSION"), op(6, "-10", "TVA")]
    effet = [
        op(7, "648360", "REMISE D'EFFETS N 7082678 A L'ESCOMPTE"),
        op(8, "-195", "DROITS DE TIMBRE SUR REMISE LCN N 7082678"),
    ]
    virement = [op(9, "25000", "VIR. RECU DE MR X REF 9010021"), op(10, "-15", "FRAIS VIREMENT")]

    assert groupes(deux_commissions, [ec(20, "-12250", "VIR 042892292")]).groupes == []
    assert groupes(tva_fausse, [ec(21, "1060", "REGLEMENT")]).groupes == []
    assert groupes(effet, [ec(22, "-648165", "REMISE LCN 7082678")]).groupes == []
    assert groupes(virement, [ec(23, "-24985", "VIR CLIENT X")]).groupes == []


def test_vat_is_ten_percent_of_the_commission_to_the_cent():
    assert tva_de_la_commission(Decimal("-175"), Decimal("-17.50"))
    assert tva_de_la_commission(Decimal("-33.33"), Decimal("-3.34"))
    assert not tva_de_la_commission(Decimal("-50"), Decimal("-10"))


def test_virement_plus_commission_plus_vat():
    banque = [
        op(1, "25000", "VIR. RECU DE MR X REF 9010021"),
        op(2, "-15", "COMMISSION VIREMENT"),
        op(3, "-1.50", "TAXE SUR VALEUR AJOUTEE"),
    ]

    assert [g.operation_ids for g in groupes(banque, [ec(8, "-24983.50", "VIR X")]).groupes] == [
        (1, 2, 3)
    ]


def test_fees_alone_never_form_a_group():
    """15/10/2026 : les frais se comptabilisent dans SIMTIS. Timbres du jour face à « DT
    D'ENREGISTREMENT », intérêt + TVA face à « FRAIS D'ESCOMPTE » : plus aucun groupe, ils
    restent « À comptabiliser »."""
    banque = [
        op(1, "-20", "DROITS DE TIMBRE SUR REMISE LCN N 2102156"),
        op(2, "-200", "DROITS DE TIMBRE SUR REMISE LCN N 7082677"),
        op(3, "-195", "DROITS DE TIMBRE SUR REMISE LCN N 7082678"),
        op(4, "-4320.95", "INTERET REMISE LCN A L'ESCOMPTE"),
        op(5, "-432.09", "TAXE SUR VALEUR AJOUTEE"),
    ]
    ecritures = [ec(8, "415", "DT D'ENREGISTREMENT"), ec(9, "4753.04", "FRAIS D'ESCOMPTE/7082678")]

    assert groupes(banque, ecritures).groupes == []


def test_a_wrong_sum_gives_no_group():
    banque = [op(1, "-10000", "CHEQUE N 2100843"), op(2, "-50", "COMMISSION")]

    assert groupes(banque, [ec(9, "10060", "CHQ° 2100843")]).groupes == []


def test_two_different_groups_make_the_entry_ambiguous():
    banque = [
        op(1, "-1000", "CHEQUE N 1111111"),
        op(2, "-1000", "PAIEMENT FOURNISSEUR"),
        op(3, "-50", "COMMISSION"),
        op(4, "-5", "TAXE SUR VALEUR AJOUTEE"),
    ]

    resultat = groupes(banque, [ec(9, "1055", "REGLEMENT")])

    assert resultat.groupes == []
    assert resultat.ecritures_ambigues == {9}


def test_identical_fee_lines_are_not_ambiguous():
    """Une opération principale et deux jeux de frais identiques : un seul groupe, pas une
    ambiguïté (les lignes sont indiscernables)."""
    banque = [
        op(1, "-1000", "VIREMENT EMIS FOURNISSEUR"),
        op(2, "-20", "COMMISSION"),
        op(3, "-2", "TAXE SUR VALEUR AJOUTEE"),
        op(4, "-20", "COMMISSION"),
        op(5, "-2", "TAXE SUR VALEUR AJOUTEE"),
    ]

    [groupe] = groupes(banque, [ec(9, "1022", "VIREMENT FOURNISSEUR")]).groupes

    assert len(groupe.operation_ids) == 3 and 1 in groupe.operation_ids


def test_an_operation_joins_one_group_only_and_rejected_pairs_are_skipped():
    banque = [
        op(1, "-10000", "CHEQUE N 2100843"),
        op(2, "-60", "COMMISSION"),
        op(3, "-6", "TAXE SUR VALEUR AJOUTEE"),
    ]
    deux = [ec(8, "10066", "CHQ° 2100843 A"), ec(9, "10066", "CHQ° 2100843 B")]

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


def test_a_fee_alone_is_no_longer_covered_by_an_entry():
    """15/10/2026 : un frais seul face à une écriture du même montant n'est plus « déjà dans
    Sage » : il se comptabilise dans SIMTIS."""
    agios = op(1, "-30", "AGIOS BANCAIRES")

    assert (
        operations_couvertes(
            [agios], [ec(10, "30", "AGIOS", jour=date(2026, 4, 23))], GRILLE_PAR_DEFAUT
        )
        == {}
    )
