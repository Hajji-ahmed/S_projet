"""Écriture corrigée dans Sage, alignée sur place (16/11/2026) : `python -m app.cli
corriger-ecriture-sage`. Cas réel : CIH, pièce RMS010004084, « EA 3442767 EL MOUAFFAK ALI »
renommée « ABS*2600067 EL IDRISSI ZAKARIYA » dans Sage, même montant, écriture dans la reprise
CIH-26-000001 : la supprimer obligeait à annuler tout le rapprochement."""

from contextlib import nullcontext
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app import cli
from app.models import AccountingEntry, AuditLog, ReconciliationMatch, ReconciliationMatchItem
from app.services import accounting_import_service, correction_ecriture_service
from app.services.errors import ConflictError
from tests.helpers import make_auth_user, save
from tests.test_accounting_import_api import account, company, xlsx

EMAIL = "mustapha@example.com"
ENTETE = ["Compte", "Date", "Journal", "N° pièce", "Libellé", "Débit", "Crédit"]
JOUR = date(2026, 7, 8)
AUTRE = ["5141", JOUR, "BQ1", "RMS084", "EAR° 0106993 YAHYA HASSAN", 10000, None]
ERRONEE = ["5141", JOUR, "BQ1", "RMS084", "EAR° EA 3442767 EL MOUAFFAK ALI", 10000, None]
CORRIGEE = ["5141", JOUR, "BQ1", "RMS084", "EAR° ABS*2600067 EL IDRISSI ZAKARIYA", 10000, None]


def fichier(*lignes: list) -> bytes:
    return xlsx([ENTETE, *lignes])


@pytest.fixture
def cih(db, reference):
    make_auth_user(reference, "COMPTABLE", email=EMAIL)
    return account(db, "CIH", "BQ1")


def importer(db, content: bytes) -> None:
    user = make_auth_user(db, "COMPTABLE")
    accounting_import_service.confirm_entries(
        db,
        company_id=company(db).id,
        fichier_nom="gl cih.xlsx",
        content=content,
        mapping=None,
        feuille=None,
        garder_doublons=None,
        ecarter_erreurs=False,
        acteur_id=user.id,
    )


def ecriture(db, libelle: str) -> AccountingEntry:
    return db.scalar(select(AccountingEntry).filter_by(libelle=libelle))


def rapprocher(db, entry: AccountingEntry) -> ReconciliationMatch:
    user = make_auth_user(db, "COMPTABLE")
    now = datetime.now(UTC)
    match = save(
        db,
        ReconciliationMatch(
            company_id=entry.company_id,
            type="N-N",
            statut="Validée",
            origine="Reprise",
            code="CIH-26-000001",
            decide_par_id=user.id,
            decide_le=now,
            valide_par_id=user.id,
            valide_le=now,
        ),
    )
    save(
        db,
        ReconciliationMatchItem(
            match_id=match.id,
            accounting_entry_id=entry.id,
            montant_affecte=Decimal("10000"),
            actif=True,
        ),
    )
    entry.statut = "Rapprochée"
    db.flush()
    return match


def analyser(db, content: bytes, ecriture_id: int, **options):
    return correction_ecriture_service.analyser(
        db,
        code_societe="SIMTIS",
        fichier_nom="gl cih.xlsx",
        content=content,
        ecriture_id=ecriture_id,
        **options,
    )


@pytest.fixture
def run(db, monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "SessionLocal", lambda: nullcontext(db))

    def _run(content: bytes, ecriture_id: int, *options: str) -> tuple[int, str, str]:
        (tmp_path / "gl cih.xlsx").write_bytes(content)
        code = cli.main(
            [
                "corriger-ecriture-sage",
                "--societe",
                "SIMTIS",
                "--fichier",
                str(tmp_path / "gl cih.xlsx"),
                "--ecriture",
                str(ecriture_id),
                *options,
            ]
        )
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return _run


def test_simulation_shows_the_change_and_writes_nothing(db, cih, run):
    importer(db, fichier(AUTRE, ERRONEE))
    entry = ecriture(db, ERRONEE[4])
    rapprocher(db, entry)

    code, out, _ = run(fichier(AUTRE, CORRIGEE), entry.id)

    assert code == 0, out
    assert "Rapprochement conservé : CIH-26-000001" in out
    assert "ABS*2600067 EL IDRISSI ZAKARIYA" in out
    assert "Simulation" in out
    assert db.get(AccountingEntry, entry.id).libelle == ERRONEE[4]


def test_apply_aligns_the_entry_and_keeps_its_reconciliation(db, cih, run):
    importer(db, fichier(AUTRE, ERRONEE))
    entry = ecriture(db, ERRONEE[4])
    match = rapprocher(db, entry)
    ancien_hash = entry.hash_ligne

    code, out, _ = run(
        fichier(AUTRE, CORRIGEE), entry.id, "--appliquer", "--motif", "GL CIH", "--email", EMAIL
    )

    assert code == 0, out
    corrigee = db.get(AccountingEntry, entry.id)
    assert corrigee.libelle == CORRIGEE[4]
    assert corrigee.hash_ligne != ancien_hash
    assert (corrigee.statut, corrigee.debit) == ("Rapprochée", Decimal("10000.00"))
    item = db.scalar(select(ReconciliationMatchItem).filter_by(accounting_entry_id=entry.id))
    assert (item.match_id, item.actif) == (match.id, True)
    # Le grand livre réimporté : la ligne corrigée est un doublon, plus aucune écriture absente
    analysis = accounting_import_service.analyse_entries(
        db, company_id=company(db).id, fichier_nom="gl.xlsx", content=fichier(AUTRE, CORRIGEE)
    )
    assert [line.statut for line in analysis.lignes] == ["Doublon", "Doublon"]
    assert analysis.ecritures_absentes == []
    [audit] = db.scalars(select(AuditLog).filter_by(action="correction_ecriture_sage")).all()
    assert audit.ancienne_valeur["libelle"] == ERRONEE[4]
    assert audit.nouvelle_valeur["libelle"] == CORRIGEE[4]
    assert audit.nouvelle_valeur["rapprochement"] == "CIH-26-000001"
    assert (audit.nouvelle_valeur["motif"], audit.nouvelle_valeur["ligne"]) == ("GL CIH", 3)


def test_apply_needs_a_motif_and_an_author(db, cih, run):
    importer(db, fichier(AUTRE, ERRONEE))
    entry = ecriture(db, ERRONEE[4])

    code, out, _ = run(fichier(AUTRE, CORRIGEE), entry.id, "--appliquer")

    assert code == 1
    assert "--motif et --email sont obligatoires" in out
    assert db.get(AccountingEntry, entry.id).libelle == ERRONEE[4]


def test_an_entry_still_in_the_file_is_refused(db, cih):
    importer(db, fichier(AUTRE, ERRONEE))
    entry = ecriture(db, AUTRE[4])

    with pytest.raises(ConflictError, match="n'est pas absente de ce grand livre"):
        analyser(db, fichier(AUTRE, CORRIGEE), entry.id)


def test_an_entry_deleted_from_sage_has_no_replacement(db, cih):
    importer(db, fichier(AUTRE, ERRONEE))
    entry = ecriture(db, ERRONEE[4])
    autre_montant = [*CORRIGEE[:5], 9000, None]

    with pytest.raises(ConflictError, match="supprimée de Sage, pas corrigée"):
        analyser(db, fichier(AUTRE, autre_montant), entry.id)


def test_two_possible_lines_need_the_line_number(db, cih):
    importer(db, fichier(AUTRE, ERRONEE))
    entry = ecriture(db, ERRONEE[4])
    deuxieme = [*CORRIGEE[:4], "EAR° 9999999 AUTRE CLIENT", 10000, None]
    content = fichier(AUTRE, CORRIGEE, deuxieme)

    with pytest.raises(ConflictError, match="Plusieurs lignes possibles"):
        analyser(db, content, entry.id)
    bilan = analyser(db, content, entry.id, ligne=4)

    assert bilan.apres["libelle"] == deuxieme[4]
