"""Reprise d'un état de rapprochement tenu sous Excel (27/10/2026) : `python -m app.cli
reprise-rapprochement`. Les fichiers listent ce qui reste non rapproché ; tout le reste du compte
passe « Rapprochée » dans un rapprochement validé « Reprise », qui doit s'équilibrer."""

from contextlib import nullcontext
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import Workbook
from sqlalchemy import select

from app import cli
from app.models import AuditLog, ReconciliationMatch
from app.schemas.reconciliation import CorrespondanceOut
from app.services import reconciliation_service, reprise_service
from app.services.reprise_service import LigneFichier, LigneSimtis, associer, cle
from tests.helpers import make_auth_user
from tests.test_reconciliation_api import account, ecriture, operation

JOUR = date(2026, 9, 10)
EMAIL = "mustapha@example.com"


def classeur(*feuilles: tuple[str, list[list]]) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    for nom, lignes in feuilles:
        ws = wb.create_sheet(nom)
        for ligne in lignes:
            ws.append(ligne)
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def jour(n: int = 0) -> datetime:
    return datetime.combine(JOUR + timedelta(days=n), datetime.min.time())


EN_TETE_BANQUE = ["DATE", "LIBELLE", "DEBIT", "CREDIT"]
EN_TETE_COMPTA = ["DATE", "LIBELLE", "DEBIT", "CREDIT", "N° DE PIECES", "echeance"]


def fichier_banque(*lignes: list) -> bytes:
    # Fichier vu de l'autre côté : le DEBIT est un crédit du relevé
    return classeur(
        ("bp au 300926", [[None], [None, None, None, "#REF!"], EN_TETE_BANQUE, *lignes])
    )


def fichier_compta(*lignes: list) -> bytes:
    return classeur(
        ("bp au 300926", [EN_TETE_BANQUE, [jour(), "AUTRE FEUILLE", 1, None]]),
        (
            "COMPTA",
            [[None], EN_TETE_COMPTA, ["SOLDE BANCAIRE AU 30/09/2026", None, 4327546], *lignes],
        ),
    )


@pytest.fixture
def run(db, monkeypatch, capsys, tmp_path):
    """Lance la commande avec ces deux fichiers ; retourne (code, sortie, erreurs)."""
    monkeypatch.setattr(cli, "SessionLocal", lambda: nullcontext(db))

    def _run(compte, banque: bytes, compta: bytes, *options: str) -> tuple[int, str, str]:
        (tmp_path / "banque.xlsx").write_bytes(banque)
        (tmp_path / "compta.xlsx").write_bytes(compta)
        code = cli.main(
            [
                "reprise-rapprochement",
                "--compte", compte.numero,
                "--banque", str(tmp_path / "banque.xlsx"),
                "--compta", str(tmp_path / "compta.xlsx"),
                "--jusqu-au", "2026-09-30",
                *options,
            ]
        )  # fmt: skip
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return _run


@pytest.fixture
def situation(reference):
    """Un compte : une opération et deux écritures restent non rapprochées (dans les fichiers),
    deux opérations et deux écritures sont à rapprocher (−1 609,50 + 500 = −1 109,50 des deux
    côtés)."""
    db = reference
    make_auth_user(db, "COMPTABLE", email=EMAIL)
    compte = account(db)
    gardee = operation(db, compte, montant="3000", jour=JOUR, libelle="REMISEDEFFETSN5812970")
    reprises = [
        operation(db, compte, montant="-1609.50", jour=JOUR, libelle="ORDRE DE VIREMENT 0326254"),
        operation(db, compte, montant="500", jour=JOUR, libelle="VERSEMENT DEPLACE"),
    ]
    vir = ecriture(
        db, compte, montant="-28865", jour=JOUR, libelle="VIR 4107860", numero_piece="SRC1"
    )
    sans_date = ecriture(
        db, compte, montant="-10000", jour=JOUR, libelle="EAR° 1020", numero_piece="RMS89"
    )
    a_rapprocher = [
        ecriture(db, compte, montant="1609.50", jour=JOUR, libelle="VIR FOURNISSEUR", numero_piece="F1"),
        # Dans le fichier sans montant : déjà pointée, elle passe dans la reprise
        ecriture(db, compte, montant="-500", jour=JOUR, libelle="ESP TT26", numero_piece="SRC2"),
    ]  # fmt: skip
    banque = fichier_banque(
        [None, None, 0, None],
        [jour(), "REMISE D'EFFETS N 5812970", 3000, None],
    )
    compta = fichier_compta(
        [jour(), "VIR 4107860", None, 28865, "SRC1", jour()],
        [jour(), "ESP TT26", None, None, "SRC2", jour()],
        [None, None, None, 10000, "RMS89", jour()],
    )
    return {
        "db": db,
        "compte": compte,
        "gardee": gardee,
        "reprises": reprises,
        "gardees_ecr": [vir, sans_date],
        "ecr_reprises": a_rapprocher,
        "banque": banque,
        "compta": compta,
    }


# --- Lecture des fichiers -------------------------------------------------------------------------


def test_the_files_are_read_with_debit_and_credit_inverted(situation):
    nom, banque = reprise_service.lire(situation["banque"], avec_piece=False)
    assert nom == "bp au 300926"
    assert [(ligne.libelle, ligne.debit, ligne.credit) for ligne in banque] == [
        ("REMISE D'EFFETS N 5812970", None, Decimal("3000.00"))
    ]

    nom, compta = reprise_service.lire(situation["compta"], avec_piece=True)
    assert nom == "COMPTA"
    assert [(ligne.date, ligne.piece, ligne.debit, ligne.sans_montant) for ligne in compta] == [
        (JOUR, "SRC1", Decimal("28865.00"), False),
        (JOUR, "SRC2", None, True),
        (None, "RMS89", Decimal("10000.00"), False),
    ]


def test_a_file_without_the_columns_is_refused():
    from app.services.errors import ConflictError

    with pytest.raises(ConflictError, match="DATE, LIBELLE, DEBIT, CREDIT et N° DE PIECES"):
        reprise_service.lire(fichier_banque([jour(), "X", 1, None]), avec_piece=True)


# --- Lignes retrouvées (règles pures) -------------------------------------------------------------


def _fichier(n: int, libelle: str, quand: date | None, credit: str, piece: str | None = None):
    return LigneFichier(n, quand, libelle, piece, None, Decimal(credit))


def _simtis(i: int, libelle: str, quand: date, credit: str, piece: str = ""):
    return LigneSimtis(i, quand, cle(libelle), cle(piece), Decimal("0"), Decimal(credit))


def test_labels_are_compared_without_spaces_and_the_exact_date_wins():
    lignes = [
        _fichier(1, "ENCAISSEMENT CHEQUE N 0576794", JOUR + timedelta(days=1), "100"),
        _fichier(2, "ENCAISSEMENT CHEQUE N 0576794", JOUR, "100"),
    ]
    simtis = [
        _simtis(10, "ENCAISSEMENTCHEQUEN0576794", JOUR, "100"),
        _simtis(11, "ENCAISSEMENTCHEQUEN0576794", JOUR - timedelta(days=1), "100"),
    ]

    trouvees, introuvables = associer(lignes, simtis, par_piece=False)

    # La ligne du jour exact prend l'opération du jour, l'autre (à 2 jours) celle de la veille
    assert trouvees == {2: 10, 1: 11}
    assert introuvables == []


def test_a_line_beyond_the_tolerance_or_with_another_amount_is_not_found():
    lignes = [
        _fichier(1, "VIR", JOUR + timedelta(days=4), "100"),
        _fichier(2, "VIR", JOUR, "99"),
    ]

    trouvees, introuvables = associer(lignes, [_simtis(10, "VIR", JOUR, "100")], par_piece=False)

    assert trouvees == {}
    assert [ligne.ligne for ligne in introuvables] == [1, 2]


def test_an_entry_is_found_by_its_piece_preferring_the_same_label():
    lignes = [_fichier(1, "EAR1 ADI 1800175", JOUR, "500", piece="RMS122")]
    simtis = [
        _simtis(10, "EAR1 AUTRE", JOUR, "500", piece="RMS122"),
        _simtis(11, "EAR1° ADI 1800175", JOUR, "500", piece="RMS122"),
    ]

    trouvees, _ = associer(lignes, simtis, par_piece=True)

    assert trouvees == {1: 11}


# --- Simulation et application ------------------------------------------------------------------


def test_the_simulation_writes_nothing(run, situation):
    code, out, _ = run(situation["compte"], situation["banque"], situation["compta"])

    assert code == 0, out
    assert "Restent non rapprochées : 1 opérations, 2 écritures" in out
    assert "Passent « Rapprochée » : 2 opérations" in out
    assert "écart 0.00" in out
    assert "Simulation" in out
    db = situation["db"]
    assert db.scalar(select(ReconciliationMatch).filter_by(origine="Reprise")) is None
    for tx in situation["reprises"]:
        db.refresh(tx)
        assert tx.statut == "Non rapprochée"


def test_apply_reconciles_everything_else_in_one_balanced_match(run, situation):
    code, out, err = run(
        situation["compte"], situation["banque"], situation["compta"],
        "--appliquer", "--motif", "Reprise au 30/09/2026", "--email", EMAIL,
    )  # fmt: skip

    assert code == 0, out + err
    db = situation["db"]
    match = db.scalar(select(ReconciliationMatch).filter_by(origine="Reprise"))
    assert (match.statut, match.type, match.commentaire) == (
        "Validée",
        "N-N",
        "Reprise au 30/09/2026",
    )
    assert match.code.startswith("AWB-26-")
    assert f"rapprochement {match.code}" in out
    for ligne in situation["reprises"] + situation["ecr_reprises"]:
        db.refresh(ligne)
        assert ligne.statut == "Rapprochée"
    for ligne in [situation["gardee"], *situation["gardees_ecr"]]:
        db.refresh(ligne)
        assert ligne.statut == "Non rapprochée"
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "reprise_rapprochement"))
    assert audit.nouvelle_valeur["nb_operations"] == 2
    assert audit.nouvelle_valeur["nb_ecritures"] == 2
    assert audit.nouvelle_valeur["fichier_banque"] == "banque.xlsx"
    assert audit.nouvelle_valeur["operations_gardees"] == [situation["gardee"].id]

    # Elle s'annule comme un autre rapprochement : tout redevient « Non rapprochée »
    user_id = audit.user_id
    reconciliation_service.cancel(db, match.id, motif="Erreur", acteur_id=user_id, ip=None)
    for ligne in situation["reprises"] + situation["ecr_reprises"]:
        db.refresh(ligne)
        assert ligne.statut == "Non rapprochée"


def test_a_line_of_the_files_missing_in_simtis_blocks_everything(run, situation):
    compta = fichier_compta(
        [jour(), "VIR 4107860", None, 28865, "SRC1", jour()],
        [jour(), "INCONNUE", None, 777, "X9", jour()],
    )

    code, out, err = run(
        situation["compte"], situation["banque"], compta,
        "--appliquer", "--motif", "Reprise", "--email", EMAIL,
    )  # fmt: skip

    assert code == 1
    assert "Comptabilité, introuvable dans SIMTIS" in err
    assert "INCONNUE" in err
    assert situation["db"].scalar(select(ReconciliationMatch).filter_by(origine="Reprise")) is None


def test_an_unbalanced_reprise_is_refused(run, situation):
    db = situation["db"]
    ecriture(db, situation["compte"], montant="-1", jour=JOUR, libelle="EN TROP", numero_piece="Z")

    code, out, _ = run(situation["compte"], situation["banque"], situation["compta"])

    assert code == 1
    assert "La reprise ne s'équilibre pas" in out


def test_a_kept_line_already_reconciled_is_left_alone(run, situation):
    db = situation["db"]
    gardee = situation["gardee"]
    gardee.statut = "Rapprochée"
    db.flush()

    _, out, _ = run(situation["compte"], situation["banque"], situation["compta"])

    assert f"Opération n° {gardee.id} (Rapprochée)" in out


# --- Affichage d'un rapprochement de milliers de lignes -------------------------------------------


def test_a_large_match_sends_twenty_lines_per_side_with_the_full_counts(run, reference):
    db = reference
    make_auth_user(db, "COMPTABLE", email=EMAIL)
    compte = account(db)
    for n in range(25):
        operation(db, compte, montant="10", jour=JOUR, libelle=f"VERSEMENT {n}")
        ecriture(db, compte, montant="-10", jour=JOUR, libelle=f"ESP {n}", numero_piece=f"P{n}")
    code, out, err = run(
        compte, fichier_banque(), fichier_compta(),
        "--appliquer", "--motif", "Reprise", "--email", EMAIL,
    )  # fmt: skip
    assert code == 0, out + err
    match = db.scalar(select(ReconciliationMatch).filter_by(origine="Reprise"))

    sortie = CorrespondanceOut.from_view(reconciliation_service.get_match_view(db, match.id))

    assert len(sortie.operations) == len(sortie.ecritures) == 20
    assert (sortie.nb_operations, sortie.nb_ecritures) == (25, 25)
    assert (sortie.total_operations, sortie.total_ecritures, sortie.ecart) == (
        Decimal("250"),
        Decimal("-250"),
        Decimal("0"),
    )


# --- Solde d'ouverture comptable (30/10/2026) -----------------------------------------------------


@pytest.fixture
def avec_ouverture(situation):
    """La ligne d'ouverture du relevé (5 000 au crédit) n'a pas d'écriture en face : sa
    contrepartie est le solde d'ouverture comptable du compte (5 000 au débit Sage)."""
    db, compte = situation["db"], situation["compte"]
    situation["ouverture"] = operation(
        db, compte, montant="5000", jour=JOUR - timedelta(days=30), libelle="RAPPROCHEMENT BLOC"
    )
    compte.date_solde_comptable = JOUR - timedelta(days=30)
    compte.solde_comptable_ouverture = Decimal("5000.00")
    db.flush()
    return situation


def test_without_the_option_the_opening_line_unbalances_the_reprise(run, avec_ouverture):
    s = avec_ouverture

    code, out, _ = run(s["compte"], s["banque"], s["compta"])

    assert code == 1
    assert "écart 5000.00" in out


def test_the_opening_balance_faces_the_opening_line(run, avec_ouverture):
    s = avec_ouverture

    code, out, err = run(
        s["compte"], s["banque"], s["compta"], "--avec-solde-ouverture",
        "--appliquer", "--motif", "Reprise au 30/09/2026", "--email", EMAIL,
    )  # fmt: skip

    assert code == 0, out + err
    assert "Solde d'ouverture comptable au 11/08/2026 : 5000.00" in out
    db = s["db"]
    match = db.scalar(select(ReconciliationMatch).filter_by(origine="Reprise"))
    assert match.statut == "Validée"
    assert (
        "solde d'ouverture comptable au 11/08/2026 (5000.00)" in match.detail_score["explication"]
    )
    for ligne in [s["ouverture"], *s["reprises"], *s["ecr_reprises"]]:
        db.refresh(ligne)
        assert ligne.statut == "Rapprochée"
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "reprise_rapprochement"))
    assert audit.nouvelle_valeur["solde_ouverture"] == "5000.00"
    assert audit.nouvelle_valeur["date_solde_ouverture"] == "2026-08-11"


def test_the_option_without_an_opening_balance_is_refused(run, situation):
    code, out, _ = run(
        situation["compte"], situation["banque"], situation["compta"], "--avec-solde-ouverture"
    )

    assert code == 1
    assert "pas de solde d'ouverture comptable" in out


def test_an_opening_balance_after_the_state_date_is_refused(run, avec_ouverture):
    s = avec_ouverture
    s["compte"].date_solde_comptable = date(2026, 10, 15)
    s["db"].flush()

    code, out, _ = run(s["compte"], s["banque"], s["compta"], "--avec-solde-ouverture")

    assert code == 1
    assert "daté du 15/10/2026, après la date de l'état" in out
