"""Reprise de l'échéance Sage d'écritures déjà importées (04/11/2026) : `python -m app.cli
completer-echeances`. Le grand livre AWB titre sa colonne d'échéance par une date : l'import ne
l'a pas lue, la commande la reprend en retrouvant chaque écriture par son empreinte."""

from contextlib import nullcontext
from datetime import date

import pytest
from sqlalchemy import select

from app import cli
from app.models import AccountingEntry, AuditLog
from app.services import accounting_import_service, echeance_service
from app.services.errors import ConflictError
from tests.helpers import make_auth_user, xls
from tests.test_accounting_import_api import account, company, xlsx

EMAIL = "mustapha@example.com"
TITRE_DATE = date(2025, 12, 31)  # titre de la colonne d'échéance, comme dans le GL AWB
ENTETE = ["Compte", "Date", "Journal", "N° pièce", "Libellé", TITRE_DATE, "Débit", "Crédit"]
LIGNES = [
    ["5141", date(2026, 9, 2), "BQ1", "SRC1", "ESP 1328867592", date(2026, 9, 1), 4000, None],
    ["5141", date(2026, 9, 3), "BQ1", "AW1", "VIREMENTS DE FONDS", None, None, 15000],
    ["5141", date(2026, 9, 4), "BQ1", "SRC2", "VIR ORDRE OTMANI", date(2026, 9, 3), 20000, None],
]


def fichier(*lignes: list) -> bytes:
    return xlsx([ENTETE, *lignes])


@pytest.fixture
def awb(db, reference):
    make_auth_user(reference, "COMPTABLE", email=EMAIL)
    return account(db, "AWB", "BQ1")


def importer(db, content: bytes, nom: str = "gl awb.xlsx") -> None:
    """Import tel qu'il a été fait : la colonne titrée par une date n'est pas reconnue."""
    user = make_auth_user(db, "COMPTABLE")
    accounting_import_service.confirm_entries(
        db,
        company_id=company(db).id,
        fichier_nom=nom,
        content=content,
        mapping=None,
        feuille=None,
        garder_doublons=None,
        ecarter_erreurs=False,
        acteur_id=user.id,
    )


def echeances(db) -> dict[str, date | None]:
    return {e.numero_piece: e.echeance for e in db.scalars(select(AccountingEntry))}


@pytest.fixture
def run(db, monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "SessionLocal", lambda: nullcontext(db))

    def _run(content: bytes, *options: str, nom: str = "gl awb.xlsx") -> tuple[int, str, str]:
        (tmp_path / nom).write_bytes(content)
        code = cli.main(
            [
                "completer-echeances",
                "--societe",
                "SIMTIS",
                "--fichier",
                str(tmp_path / nom),
                *options,
            ]
        )
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return _run


def test_the_import_did_not_read_the_column_titled_by_a_date(db, awb):
    importer(db, fichier(*LIGNES))

    assert echeances(db) == {"SRC1": None, "AW1": None, "SRC2": None}


def test_simulation_writes_nothing(db, awb, run):
    importer(db, fichier(*LIGNES))

    code, out, _ = run(fichier(*LIGNES))

    assert code == 0
    assert "échéance en colonne F" in out
    assert "Échéances à remplir : 2" in out
    assert "Simulation" in out
    assert echeances(db) == {"SRC1": None, "AW1": None, "SRC2": None}


def test_apply_fills_the_empty_due_dates_with_an_audit(db, awb, run):
    importer(db, fichier(*LIGNES))

    code, out, _ = run(fichier(*LIGNES), "--appliquer", "--motif", "GL AWB", "--email", EMAIL)

    assert code == 0, out
    assert echeances(db) == {"SRC1": date(2026, 9, 1), "AW1": None, "SRC2": date(2026, 9, 3)}
    audits = db.scalars(select(AuditLog).filter_by(action="completer_echeance")).all()
    assert len(audits) == 2
    assert audits[0].ancienne_valeur == {"echeance": None}
    assert audits[0].nouvelle_valeur["motif"] == "GL AWB"
    assert audits[0].nouvelle_valeur["fichier"] == "gl awb.xlsx"


def test_a_xls_file_is_read_too(db, awb, run):
    content = xls(("Sage", [ENTETE, *LIGNES]))
    importer(db, content, "gl awb.xls")

    code, out, _ = run(
        content, "--appliquer", "--motif", "GL AWB", "--email", EMAIL, nom="gl awb.xls"
    )

    assert code == 0, out
    assert echeances(db)["SRC1"] == date(2026, 9, 1)


def test_an_existing_due_date_is_kept_and_reported(db, awb, run):
    importer(db, fichier(*LIGNES))
    entry = db.scalar(select(AccountingEntry).filter_by(numero_piece="SRC1"))
    entry.echeance = date(2026, 8, 30)
    db.flush()

    code, out, _ = run(fichier(*LIGNES), "--appliquer", "--motif", "GL AWB", "--email", EMAIL)

    assert code == 0
    assert echeances(db)["SRC1"] == date(2026, 8, 30)
    assert echeances(db)["SRC2"] == date(2026, 9, 3)
    assert "Déjà remplies, différentes (gardées) : 1" in out
    assert "30/08/2026 gardée (fichier 01/09/2026)" in out


def test_lines_without_an_entry_are_only_listed(db, awb, run):
    importer(db, fichier(*LIGNES[:2]))

    code, out, _ = run(fichier(*LIGNES), "--appliquer", "--motif", "GL AWB", "--email", EMAIL)

    assert code == 0
    assert "Lignes du fichier sans écriture dans SIMTIS : 1" in out
    assert "Non trouvée : ligne 4 · 04/09/2026 · SRC2 · VIR ORDRE OTMANI" in out
    assert echeances(db) == {"SRC1": date(2026, 9, 1), "AW1": None}


def test_entries_of_another_company_are_never_touched(db, awb, run):
    importer(db, fichier(*LIGNES))
    for entry in db.scalars(select(AccountingEntry)):
        entry.company_id = company(db, "SOCX").id
    db.flush()

    code, out, _ = run(fichier(*LIGNES), "--appliquer", "--motif", "GL AWB", "--email", EMAIL)

    assert code == 0
    assert "Échéances à remplir : 0" in out
    assert set(echeances(db).values()) == {None}


def test_two_columns_titled_by_a_date_need_the_letter(db, awb, run):
    entete = [*ENTETE, date(2026, 1, 1)]
    lignes = [[*ligne, None] for ligne in LIGNES]
    importer(db, xlsx([entete, *lignes]))

    code, _, err = run(xlsx([entete, *lignes]))
    assert code == 1
    assert "Colonnes titrées par une date : F, I" in err

    code, out, _ = run(xlsx([entete, *lignes]), "--colonne-echeance", "f")
    assert code == 0
    assert "Échéances à remplir : 2" in out


def test_no_column_titled_by_a_date(db, awb, run):
    entete = [*ENTETE[:5], "Divers", *ENTETE[6:]]

    code, _, err = run(xlsx([entete, *LIGNES]))

    assert code == 1
    assert "Colonnes titrées par une date : aucune" in err


def test_apply_needs_a_motif_and_an_email(db, awb, run):
    importer(db, fichier(*LIGNES))

    code, out, _ = run(fichier(*LIGNES), "--appliquer")

    assert code == 1
    assert "--motif et --email sont obligatoires" in out
    assert set(echeances(db).values()) == {None}


def test_unknown_author_is_refused(db, awb, run):
    importer(db, fichier(*LIGNES))

    code, _, err = run(
        fichier(*LIGNES), "--appliquer", "--motif", "GL AWB", "--email", "x@example.com"
    )

    assert code == 1
    assert "Utilisateur introuvable" in err
    assert set(echeances(db).values()) == {None}


def test_colonne_echeance_reads_a_letter():
    assert echeance_service.colonne_echeance(("a", "b"), "J") == 9
    with pytest.raises(ConflictError):
        echeance_service.colonne_echeance(("a",), "1")


def test_columns_the_model_does_not_know_are_given_by_letter(db, awb, run):
    """Les titres du GL AWB : « compt », « journale »… ne sont pas reconnus sans modèle."""
    entete = ["compt", "date", "journale", "n piece", "libelle", TITRE_DATE, "debit", "credit"]
    importer(db, fichier(*LIGNES))
    content = xlsx([entete, *LIGNES])

    code, _, err = run(content)
    assert code == 1
    assert "Colonne obligatoire non associée" in err

    code, out, _ = run(content, "--colonne", "compte=A", "--colonne", "journal=C")
    assert code == 0, out
    assert "Compte : A" in out
    assert "Échéances à remplir : 2" in out

    code, _, err = run(content, "--colonne", "inconnu=A")
    assert code == 1
    assert "Champ inconnu" in err
