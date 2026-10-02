"""Import des relevés : analyse et aperçu (P7.1), puis confirmation et enregistrement (P7.2)."""

import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from itertools import count

import pytest
from openpyxl import Workbook, load_workbook
from sqlalchemy import func, select

from app.models import (
    AuditLog,
    BalanceCheck,
    Bank,
    BankAccount,
    BankAccountBalance,
    BankStatement,
    BankTransaction,
    ColumnMapping,
    Company,
    ImportBatch,
    PointageType,
)
from app.services.position_service import business_today
from tests.helpers import bearer, build_account, login, make_auth_user, save

URL = "/api/statements/import/analyse"
TODAY = business_today()
_numeros = count(1)

HEADER = ["Date opération", "Date valeur", "Libellé", "Débit", "Crédit", "Solde"]
STATEMENT = [
    ["ATTIJARIWAFA BANK - Relevé de compte"],
    ["Compte", "007 780 0001234500000123 45"],
    [],
    HEADER,
    [date(2026, 9, 24), date(2026, 9, 24), "VIR RECU CLIENT ABC REF: VR-001", None, 50000, 1050000],
    ["25/09/2026", "25/09/2026", "CHQ N° 1234567 FOURNISSEUR X", "12 500,50", None, 1037499.5],
    [date(2026, 9, 26), None, "frais   tenue de compte", 150, None, 1037349.5],
    [None, None, "TOTAL", 12650.5, 50000, None],
]


def xlsx(*sheets: tuple[str, list[list]]) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for title, rows in sheets:
        sheet = workbook.create_sheet(title)
        for row in rows:
            sheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def tresorerie(client, reference) -> dict[str, str]:
    make_auth_user(reference, "TRESORERIE", email="tresorerie@example.com")
    return bearer(login(client, "tresorerie@example.com"))


@pytest.fixture
def account(db, reference) -> BankAccount:
    company = db.scalar(select(Company).filter_by(code="SIMTIS"))
    bank = db.scalar(select(Bank).filter_by(code="CIH"))
    return save(db, build_account(company, bank, numero=f"RIB-IMPORT-{next(_numeros):06d}"))


def analyse(client, headers, account_id, content, *, nom="releve.xlsx", **form):
    data = {"bank_account_id": str(account_id), **form}
    if isinstance(data.get("mapping"), dict):
        data["mapping"] = json.dumps(data["mapping"])
    files = {"fichier": (nom, content, "application/octet-stream")}
    return client.post(URL, data=data, files=files, headers=headers)


def counts(db) -> tuple[int, ...]:
    return tuple(
        db.scalar(select(func.count()).select_from(model))
        for model in (ImportBatch, BankStatement, BankTransaction, AuditLog)
    )


# --- Lecture d'un relevé standard ----------------------------------------------------------------


def test_statement_is_analysed_without_being_saved(client, tresorerie, account, db):
    before = counts(db)

    response = analyse(client, tresorerie, account.id, xlsx(("Relevé", STATEMENT)))

    assert response.status_code == 200, response.text
    body = response.json()
    assert counts(db) == before  # rien n'est enregistré, pas même l'audit
    assert (body["bank_code"], body["devise"], body["feuille"]) == ("CIH", "MAD", "Relevé")
    assert body["ligne_entete"] == 4  # les lignes de titre au-dessus sont ignorées
    assert body["mapping_source"] == "Détection"
    assert body["mapping"] == {
        "date_operation": 0,
        "date_valeur": 1,
        "libelle": 2,
        "reference": None,
        "debit": 3,
        "credit": 4,
        "montant": None,
        "solde": 5,
        "pointage": None,
        "lettrage_escompte": None,
        "commentaire": None,
        "banque": None,
    }
    assert body["erreurs_mapping"] == []
    assert [column["entete"] for column in body["colonnes"]] == HEADER
    assert body["colonnes"][0]["exemples"] == ["24/09/2026", "25/09/2026", "26/09/2026"]
    assert body["deja_importe"] is False


def test_lines_are_normalised(client, tresorerie, account):
    body = analyse(client, tresorerie, account.id, xlsx(("Relevé", STATEMENT))).json()

    first, cheque, fees = body["lignes"]
    assert [line["statut"] for line in body["lignes"]] == ["Valide"] * 3
    assert first | {"hash_ligne": None} == {
        "numero": 5,
        "statut": "Valide",
        "motifs": [],
        "date_operation": "2026-09-24",
        "date_valeur": "2026-09-24",
        "libelle": "VIR RECU CLIENT ABC REF: VR-001",
        "reference": "VR-001",
        "debit": "0.00",
        "credit": "50000.00",
        "montant": "50000.00",
        "solde": "1050000.00",
        "pointage": None,
        "pointage_type_id": None,
        "lettrage_escompte": None,
        "commentaire": None,
        "hash_ligne": None,
        "doublon_de": None,
    }
    assert (cheque["date_operation"], cheque["debit"], cheque["montant"]) == (
        "2026-09-25",
        "12500.50",
        "-12500.50",
    )
    assert cheque["reference"] == "1234567"
    assert fees["libelle"] == "FRAIS TENUE DE COMPTE"
    assert len({line["hash_ligne"] for line in body["lignes"]}) == 3


def test_summary_totals_period_and_balances(client, tresorerie, account):
    resume = analyse(client, tresorerie, account.id, xlsx(("Relevé", STATEMENT))).json()["resume"]

    assert resume == {
        "nb_lignes": 3,
        "nb_valides": 3,
        "nb_erreurs": 0,
        "nb_doublons": 0,
        "nb_ignorees": 1,  # la ligne TOTAL
        "total_debit": "12650.50",
        "total_credit": "50000.00",
        "periode_debut": "2026-09-24",
        "periode_fin": "2026-09-26",
        "solde_ouverture": "1000000.00",
        "solde_cloture": "1037349.50",
        "soldes_coherents": True,
    }


def test_newest_first_statement_gives_the_same_balances(client, tresorerie, account):
    rows = [HEADER, *reversed(STATEMENT[4:7])]

    resume = analyse(client, tresorerie, account.id, xlsx(("Relevé", rows))).json()["resume"]

    assert (resume["solde_ouverture"], resume["solde_cloture"]) == ("1000000.00", "1037349.50")
    assert resume["soldes_coherents"] is True


def test_broken_balance_chain_is_reported(client, tresorerie, account):
    rows = [HEADER, *STATEMENT[4:7]]
    rows[-1] = [*rows[-1][:5], 999]

    resume = analyse(client, tresorerie, account.id, xlsx(("Relevé", rows))).json()["resume"]

    assert resume["soldes_coherents"] is False


def test_signed_amount_column(client, tresorerie, account):
    rows = [
        ["Date", "Libellé", "Montant"],
        ["24/09/2026", "VIR RECU", "1 000,00"],
        ["25/09/2026", "PRLV", "-250"],
    ]

    body = analyse(client, tresorerie, account.id, xlsx(("Relevé", rows))).json()

    assert body["mapping"]["montant"] == 2
    assert [(line["debit"], line["credit"]) for line in body["lignes"]] == [
        ("0.00", "1000.00"),
        ("250.00", "0.00"),
    ]
    assert body["resume"]["solde_ouverture"] is None  # pas de colonne Solde
    assert body["resume"]["soldes_coherents"] is None


# --- Lignes en erreur et en double -----------------------------------------------------------------


def test_invalid_lines_are_reported_with_their_reasons(client, tresorerie, account):
    future = (TODAY + timedelta(days=2)).strftime("%d/%m/%Y")
    rows = [
        HEADER,
        ["31/02/2026", None, "DATE IMPOSSIBLE", 10, None, None],
        ["24/09/2026", None, None, 10, None, None],
        ["24/09/2026", None, "LES DEUX", 10, 20, None],
        ["24/09/2026", None, "AUCUN MONTANT", None, None, None],
        ["24/09/2026", None, "MONTANT ILLISIBLE", "dix", None, None],
        [future, None, "DANS LE FUTUR", 10, None, None],
        ["24/09/2026", None, "VALIDE", 10, None, None],
    ]

    body = analyse(client, tresorerie, account.id, xlsx(("Relevé", rows))).json()

    reasons = {line["numero"]: (line["statut"], line["motifs"]) for line in body["lignes"]}
    assert reasons[2][0] == "Erreur" and "Date illisible" in reasons[2][1][0]
    assert reasons[3] == ("Erreur", ["Libellé manquant."])
    assert reasons[4] == ("Erreur", ["Débit et crédit renseignés sur la même ligne."])
    assert reasons[5] == ("Erreur", ["Ni débit ni crédit."])
    assert reasons[6][0] == "Erreur" and reasons[6][1][0].startswith("Débit : Montant illisible")
    assert reasons[7] == ("Erreur", ["Date d'opération dans le futur."])
    assert reasons[8] == ("Valide", [])
    assert (body["resume"]["nb_erreurs"], body["resume"]["nb_valides"]) == (6, 1)
    assert body["resume"]["total_debit"] == "10.00"  # seules les lignes valides comptent


def test_identical_lines_in_the_file_are_flagged(client, tresorerie, account):
    rows = [HEADER, *[["24/09/2026", None, "FRAIS SMS", 10, None, None]] * 2]

    lines = analyse(client, tresorerie, account.id, xlsx(("Relevé", rows))).json()["lignes"]

    assert [line["statut"] for line in lines] == ["Valide", "Doublon"]
    assert lines[1]["motifs"] == ["Ligne identique à la ligne 2 du fichier."]
    assert lines[1]["doublon_de"] == 2
    # Si l'utilisateur garde les deux, elles restent distinctes
    assert lines[0]["hash_ligne"] != lines[1]["hash_ligne"]


def test_lines_already_imported_are_flagged(client, tresorerie, account, db):
    content = xlsx(("Relevé", STATEMENT))
    first = analyse(client, tresorerie, account.id, content).json()["lignes"][0]
    statement = save(db, BankStatement(bank_account_id=account.id))
    save(
        db,
        BankTransaction(
            statement_id=statement.id,
            bank_account_id=account.id,
            date_operation=date(2026, 9, 24),
            libelle=first["libelle"],
            debit=0,
            credit=50000,
            montant=50000,
            hash_ligne=first["hash_ligne"],
        ),
    )

    body = analyse(client, tresorerie, account.id, content).json()

    assert body["lignes"][0]["statut"] == "Doublon"
    assert body["lignes"][0]["motifs"] == ["Déjà importée pour ce compte."]
    assert body["resume"]["nb_doublons"] == 1


def test_already_confirmed_file_is_reported(client, tresorerie, account, db):
    content = xlsx(("Relevé", STATEMENT))
    fichier_hash = analyse(client, tresorerie, account.id, content).json()["fichier_hash"]
    save(
        db,
        ImportBatch(
            type="Banque",
            company_id=account.company_id,
            bank_account_id=account.id,
            fichier_nom="ancien.xlsx",
            fichier_hash=fichier_hash,
            statut="Confirmé",
        ),
    )

    assert analyse(client, tresorerie, account.id, content).json()["deja_importe"] is True


def test_bank_column_must_match_the_account(client, tresorerie, account):
    rows = [
        ["Banque", "Date", "Libellé", "Débit"],
        ["CIH BANK", "24/09/2026", "OK", 1],
        ["BMCE", "24/09/2026", "AUTRE BANQUE", 1],
    ]

    lines = analyse(client, tresorerie, account.id, xlsx(("Relevé", rows))).json()["lignes"]

    assert lines[0]["statut"] == "Valide"
    assert lines[1]["motifs"] == ["Banque « BMCE » différente de celle du compte (CIH)."]


# --- Correspondance des colonnes -----------------------------------------------------------------

UNKNOWN_HEADERS = [["Col1", "Col2", "Col3"], ["24/09/2026", "VIR RECU", 100]]


def test_unrecognised_columns_give_mapping_errors_and_no_lines(client, tresorerie, account):
    body = analyse(client, tresorerie, account.id, xlsx(("Relevé", UNKNOWN_HEADERS))).json()

    assert body["erreurs_mapping"] == [
        "Colonne obligatoire non associée : Date d'opération.",
        "Colonne obligatoire non associée : Libellé.",
        "Associez au moins une colonne de montant : Débit, Crédit ou Montant signé.",
    ]
    assert body["lignes"] == []


def test_user_mapping_is_applied(client, tresorerie, account):
    mapping = {"date_operation": 0, "libelle": 1, "credit": 2}

    body = analyse(
        client, tresorerie, account.id, xlsx(("Relevé", UNKNOWN_HEADERS)), mapping=mapping
    ).json()

    assert body["mapping_source"] == "Utilisateur"
    assert body["erreurs_mapping"] == []
    assert body["lignes"][0]["credit"] == "100.00"


@pytest.mark.parametrize(
    ("mapping", "error"),
    [
        (
            {"date_operation": 0, "libelle": 0, "credit": 2},
            "La colonne A est associée à plusieurs champs.",
        ),
        (
            {"date_operation": 0, "libelle": 1, "credit": 2, "montant": 2},
            "Choisissez Débit et Crédit, ou Montant signé, pas les deux.",
        ),
        (
            {"date_operation": 0, "libelle": 1, "credit": 9},
            "Crédit : colonne inexistante dans le fichier.",
        ),
    ],
)
def test_inconsistent_user_mapping_is_reported(client, tresorerie, account, mapping, error):
    body = analyse(
        client, tresorerie, account.id, xlsx(("Relevé", UNKNOWN_HEADERS)), mapping=mapping
    ).json()

    assert error in body["erreurs_mapping"]
    assert body["lignes"] == []


@pytest.mark.parametrize("mapping", ["{pas du json", '{"inconnu": 1}', '{"debit": -1}', "[1]"])
def test_malformed_mapping_gives_422(client, tresorerie, account, mapping):
    content = xlsx(("Relevé", STATEMENT))

    assert analyse(client, tresorerie, account.id, content, mapping=mapping).status_code == 422


def test_saved_bank_mapping_is_reused(client, tresorerie, account, db):
    save(
        db,
        ColumnMapping(
            type="Banque",
            bank_id=account.bank_id,
            nom="CIH standard",
            mapping={"date_operation": "Jour", "libelle": "Texte", "credit": "Entrées"},
        ),
    )
    rows = [["Jour", "Texte", "Entrées"], ["24/09/2026", "VIR RECU", 100]]

    body = analyse(client, tresorerie, account.id, xlsx(("Relevé", rows))).json()

    assert body["mapping_source"] == "Modèle de la banque"
    assert (body["mapping"]["date_operation"], body["mapping"]["credit"]) == (0, 2)
    assert body["lignes"][0]["statut"] == "Valide"


def test_sheet_can_be_chosen(client, tresorerie, account):
    content = xlsx(("Couverture", [["Relevé de septembre"]]), ("Opérations", STATEMENT))

    default = analyse(client, tresorerie, account.id, content).json()
    chosen = analyse(client, tresorerie, account.id, content, feuille="Opérations").json()
    unknown = analyse(client, tresorerie, account.id, content, feuille="Autre")

    assert default["feuilles"] == ["Couverture", "Opérations"]
    assert default["erreurs_mapping"] != []  # la première feuille n'est pas un relevé
    assert chosen["resume"]["nb_valides"] == 3
    assert unknown.status_code == 409
    assert unknown.json() == {"detail": "Feuille introuvable dans le fichier : « Autre »."}


# --- Fichier et compte refusés -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("nom", "content", "detail"),
    [
        ("releve.csv", b"Date;Libelle", "Seuls les fichiers Excel .xlsx sont acceptés."),
        ("releve.xlsx", b"", "Le fichier est vide."),
        (
            "releve.xlsx",
            b"pas un classeur",
            "Fichier illisible : ce n'est pas un classeur Excel .xlsx valide.",
        ),
        ("releve.xlsx", b"x" * (5 * 1024 * 1024 + 1), "Fichier trop volumineux : 5 Mo au plus."),
    ],
)
def test_refused_file_gives_409(client, tresorerie, account, nom, content, detail):
    response = analyse(client, tresorerie, account.id, content, nom=nom)

    assert response.status_code == 409
    assert response.json() == {"detail": detail}


def test_empty_sheet_gives_409(client, tresorerie, account):
    response = analyse(client, tresorerie, account.id, xlsx(("Vide", [])))

    assert response.status_code == 409


def test_inactive_account_gives_409(client, tresorerie, account, db):
    account.actif = False
    db.flush()

    response = analyse(client, tresorerie, account.id, xlsx(("Relevé", STATEMENT)))

    assert response.status_code == 409
    assert "inactif" in response.json()["detail"]


def test_unknown_account_gives_404(client, tresorerie):
    assert analyse(client, tresorerie, 999999, xlsx(("Relevé", STATEMENT))).status_code == 404


@pytest.mark.parametrize("role", ["DIRECTION", "COMPTABLE"])
def test_roles_without_import_permission_get_403(client, reference, account, role):
    make_auth_user(reference, role, email=f"{role.lower()}@example.com")
    headers = bearer(login(client, f"{role.lower()}@example.com"))

    response = analyse(client, headers, account.id, xlsx(("Relevé", STATEMENT)))

    assert response.status_code == 403


# --- Confirmation (P7.2) ---------------------------------------------------------------------------

CONFIRM_URL = "/api/statements/import/confirm"
CLOSING_DAY = date(2026, 9, 26)


def confirm(client, headers, account_id, content, *, nom="releve.xlsx", **form):
    data = {"bank_account_id": str(account_id)}
    for key, value in form.items():
        data[key] = json.dumps(value) if isinstance(value, dict | list) else str(value).lower()
    files = {"fichier": (nom, content, "application/octet-stream")}
    return client.post(CONFIRM_URL, data=data, files=files, headers=headers)


def transactions(db, account) -> list[BankTransaction]:
    query = select(BankTransaction).filter_by(bank_account_id=account.id)
    return list(db.scalars(query.order_by(BankTransaction.id)))


def day_balance(db, account, jour=CLOSING_DAY) -> BankAccountBalance | None:
    query = select(BankAccountBalance).filter_by(bank_account_id=account.id, date_solde=jour)
    return db.scalar(query)


def test_confirmation_saves_the_statement(client, tresorerie, account, db):
    response = confirm(client, tresorerie, account.id, xlsx(("Relevé", STATEMENT)))

    assert response.status_code == 201, response.text
    body = response.json()
    assert body | {"import_id": 0, "statement_id": 0} == {
        "import_id": 0,
        "statement_id": 0,
        "bank_account_id": account.id,
        "fichier_nom": "releve.xlsx",
        "nb_importees": 3,
        "nb_erreurs_ecartees": 0,
        "nb_doublons_ecartes": 0,
        "total_debit": "12650.50",
        "total_credit": "50000.00",
        "periode_debut": "2026-09-24",
        "periode_fin": "2026-09-26",
        "solde_ouverture": "1000000.00",
        "solde_cloture": "1037349.50",
        "soldes_coherents": True,
        "controle_solde": None,  # aucun solde enregistré ce jour-là : rien à comparer
        "solde_du_jour": "Créé",
        "modele_enregistre": True,
    }
    batch = db.get(ImportBatch, body["import_id"])
    assert (batch.statut, batch.type, batch.nb_lignes, batch.company_id) == (
        "Confirmé",
        "Banque",
        3,
        account.company_id,
    )
    statement = db.get(BankStatement, body["statement_id"])
    assert statement.import_batch_id == batch.id
    assert (statement.solde_ouverture, statement.solde_cloture) == (
        Decimal("1000000.00"),
        Decimal("1037349.50"),
    )
    rows = transactions(db, account)
    assert [(row.date_operation, row.debit, row.credit, row.montant) for row in rows] == [
        (date(2026, 9, 24), Decimal("0.00"), Decimal("50000.00"), Decimal("50000.00")),
        (date(2026, 9, 25), Decimal("12500.50"), Decimal("0.00"), Decimal("-12500.50")),
        (date(2026, 9, 26), Decimal("150.00"), Decimal("0.00"), Decimal("-150.00")),
    ]
    assert rows[1].reference == "1234567"
    assert all(row.statut == "Non rapprochée" and row.statement_id == statement.id for row in rows)
    balance = day_balance(db, account)
    assert (balance.solde, balance.source, balance.credit_utilise) == (
        Decimal("1037349.50"),
        "Relevé",
        None,
    )
    [entry] = db.scalars(select(AuditLog).filter_by(action="import_releve")).all()
    assert entry.entite_id == str(batch.id)
    assert entry.nouvelle_valeur["nb_lignes"] == 3
    assert entry.nouvelle_valeur["total_debit"] == "12650.50"


def test_same_file_cannot_be_confirmed_twice(client, tresorerie, account, db):
    content = xlsx(("Relevé", STATEMENT))
    confirm(client, tresorerie, account.id, content)

    again = confirm(client, tresorerie, account.id, content, nom="copie.xlsx")
    preview = analyse(client, tresorerie, account.id, content).json()

    assert again.status_code == 409
    assert again.json() == {"detail": "Ce fichier a déjà été importé pour cette société."}
    assert len(transactions(db, account)) == 3
    assert preview["deja_importe"] is True
    assert {line["statut"] for line in preview["lignes"]} == {"Doublon"}


def test_overlapping_statement_imports_only_the_new_lines(client, tresorerie, account, db):
    confirm(client, tresorerie, account.id, xlsx(("Relevé", STATEMENT)))
    new_line = ["27/09/2026", None, "VIR RECU CLIENT DEF", None, 1000, 1038349.5]
    next_rows = [HEADER, STATEMENT[6], new_line]

    body = confirm(client, tresorerie, account.id, xlsx(("Relevé", next_rows))).json()

    assert (body["nb_importees"], body["nb_doublons_ecartes"]) == (1, 1)
    assert len(transactions(db, account)) == 4


ROWS_WITH_ERROR = [*STATEMENT[:7], ["27/09/2026", None, "MONTANT ILLISIBLE", "dix", None, None]]


def test_lines_in_error_block_the_confirmation(client, tresorerie, account, db):
    before = counts(db)

    response = confirm(client, tresorerie, account.id, xlsx(("Relevé", ROWS_WITH_ERROR)))

    assert response.status_code == 409
    assert response.json() == {
        "detail": "1 ligne en erreur : corrigez le fichier, ou confirmez en les écartant."
    }
    assert counts(db) == before


def test_lines_in_error_can_be_discarded(client, tresorerie, account, db):
    response = confirm(
        client, tresorerie, account.id, xlsx(("Relevé", ROWS_WITH_ERROR)), ecarter_erreurs=True
    )

    assert response.status_code == 201
    assert (response.json()["nb_importees"], response.json()["nb_erreurs_ecartees"]) == (3, 1)
    assert db.scalar(select(ImportBatch).filter_by(bank_account_id=account.id)).nb_erreurs == 1


@pytest.mark.parametrize(("kept", "expected"), [([], 1), ([3], 2)])
def test_identical_line_in_the_file_is_kept_only_on_request(
    client, tresorerie, account, db, kept, expected
):
    rows = [HEADER, *[["24/09/2026", None, "FRAIS SMS", 10, None, None]] * 2]

    body = confirm(
        client, tresorerie, account.id, xlsx(("Relevé", rows)), garder_doublons=kept
    ).json()

    assert body["nb_importees"] == expected
    assert body["nb_doublons_ecartes"] == 2 - expected
    assert len({row.hash_ligne for row in transactions(db, account)}) == expected


def test_only_identical_lines_of_the_file_can_be_kept(client, tresorerie, account):
    response = confirm(
        client, tresorerie, account.id, xlsx(("Relevé", STATEMENT)), garder_doublons=[5]
    )

    assert response.status_code == 409
    assert "La ligne 5 n'est pas identique" in response.json()["detail"]


@pytest.mark.parametrize("value", ["[0]", "{}", "pas du json", '["a"]'])
def test_malformed_kept_lines_give_422(client, tresorerie, account, value):
    content = xlsx(("Relevé", STATEMENT))
    data = {"bank_account_id": str(account.id), "garder_doublons": value}
    files = {"fichier": ("releve.xlsx", content, "application/octet-stream")}

    assert client.post(CONFIRM_URL, data=data, files=files, headers=tresorerie).status_code == 422


def test_file_without_any_line_to_import_is_refused(client, tresorerie, account):
    rows = [HEADER, ["24/09/2026", None, "ILLISIBLE", "x", None, None]]

    response = confirm(client, tresorerie, account.id, xlsx(("Relevé", rows)), ecarter_erreurs=True)

    assert response.status_code == 409
    assert response.json() == {"detail": "Aucune ligne à importer dans ce fichier."}


def test_incomplete_mapping_refuses_the_confirmation(client, tresorerie, account):
    response = confirm(client, tresorerie, account.id, xlsx(("Relevé", UNKNOWN_HEADERS)))

    assert response.status_code == 409
    assert response.json()["detail"].startswith("Correspondance des colonnes incomplète")


# --- Contrôle et solde du jour de clôture --------------------------------------------------------


def manual_balance(db, account, solde: str) -> BankAccountBalance:
    return save(
        db,
        BankAccountBalance(
            bank_account_id=account.id,
            date_solde=CLOSING_DAY,
            solde=Decimal(solde),
            credit_utilise=Decimal("300000"),
            source="Saisie",
        ),
    )


def test_matching_recorded_balance_gives_a_conforming_check(client, tresorerie, account, db):
    manual_balance(db, account, "1037349.50")

    body = confirm(client, tresorerie, account.id, xlsx(("Relevé", STATEMENT))).json()

    assert body["controle_solde"] == {
        "statut": "Conforme",
        "date_controle": "2026-09-26",
        "solde_releve": "1037349.50",
        "solde_enregistre": "1037349.50",
        "ecart": "0.00",
        "commentaire": None,
    }
    assert body["solde_du_jour"] == "Corrigé"  # même montant, la source devient « Relevé »
    assert day_balance(db, account).source == "Relevé"


def test_different_recorded_balance_gives_a_gap_and_the_statement_wins(
    client, tresorerie, account, db
):
    manual_balance(db, account, "1000000")

    body = confirm(client, tresorerie, account.id, xlsx(("Relevé", STATEMENT))).json()

    assert (body["controle_solde"]["statut"], body["controle_solde"]["ecart"]) == (
        "Écart",
        "37349.50",
    )
    check = db.scalar(select(BalanceCheck).filter_by(bank_account_id=account.id))
    assert (check.solde_enregistre, check.bank_statement_id) == (
        Decimal("1000000.00"),
        body["statement_id"],
    )
    balance = day_balance(db, account)
    assert (balance.solde, balance.source) == (Decimal("1037349.50"), "Relevé")
    assert balance.credit_utilise == Decimal("300000.00")  # le crédit utilisé saisi est conservé
    [entry] = db.scalars(select(AuditLog).filter_by(action="correction_solde")).all()
    assert entry.ancienne_valeur == {
        "date_solde": "2026-09-26",
        "solde": "1000000.00",
        "source": "Saisie",
    }


def test_inconsistent_statement_gives_a_check_to_verify(client, tresorerie, account, db):
    manual_balance(db, account, "999")
    rows = [HEADER, *STATEMENT[4:7]]
    rows[-1] = [*rows[-1][:5], 999]

    body = confirm(client, tresorerie, account.id, xlsx(("Relevé", rows))).json()

    assert body["soldes_coherents"] is False
    assert body["controle_solde"]["statut"] == "À vérifier"
    assert body["controle_solde"]["commentaire"] is not None


def test_statement_without_balance_column_leaves_the_daily_balance_alone(
    client, tresorerie, account, db
):
    rows = [["Date", "Libellé", "Montant"], ["26/09/2026", "VIR RECU", "1 000,00"]]

    body = confirm(client, tresorerie, account.id, xlsx(("Relevé", rows))).json()

    assert (body["solde_du_jour"], body["controle_solde"]) == (None, None)
    assert day_balance(db, account) is None


# --- Modèle de correspondance et pointage --------------------------------------------------------


def test_confirmed_mapping_is_reused_for_the_next_statement(client, tresorerie, account, db):
    mapping = {"date_operation": 0, "libelle": 1, "credit": 2}
    confirm(client, tresorerie, account.id, xlsx(("Relevé", UNKNOWN_HEADERS)), mapping=mapping)
    next_file = [UNKNOWN_HEADERS[0], ["25/09/2026", "VIR RECU 2", 200]]

    body = analyse(client, tresorerie, account.id, xlsx(("Relevé", next_file))).json()

    saved = db.scalar(select(ColumnMapping).filter_by(bank_id=account.bank_id))
    assert saved.mapping == {"date_operation": "Col1", "libelle": "Col2", "credit": "Col3"}
    assert body["mapping_source"] == "Modèle de la banque"
    assert body["lignes"][0]["statut"] == "Valide"


def test_mapping_with_a_column_without_header_is_not_saved(client, tresorerie, account, db):
    rows = [["Date", "Libellé", None], ["24/09/2026", "VIR", 5]]
    mapping = {"date_operation": 0, "libelle": 1, "credit": 2}

    body = confirm(client, tresorerie, account.id, xlsx(("Relevé", rows)), mapping=mapping).json()

    assert body["modele_enregistre"] is False
    assert db.scalar(select(ColumnMapping).filter_by(bank_id=account.bank_id)) is None


def test_pointage_is_linked_to_its_type_and_left_empty_when_unknown(
    client, tresorerie, account, db
):
    rows = [
        ["Date", "Libellé", "Débit", "Pointage"],
        ["24/09/2026", "FRAIS", 10, "frais bancaires"],
        ["24/09/2026", "AUTRE", 20, "Virement interne"],
    ]
    frais = db.scalar(select(PointageType).filter_by(code="FRAIS_BANCAIRES"))

    preview = analyse(client, tresorerie, account.id, xlsx(("Relevé", rows))).json()["lignes"]
    confirm(client, tresorerie, account.id, xlsx(("Relevé", rows)))

    assert preview[0]["pointage_type_id"] == frais.id
    # Pointage inconnu : la ligne reste valide, son pointage reste vide (décision métier)
    assert (preview[1]["statut"], preview[1]["pointage_type_id"]) == ("Valide", None)
    assert [row.pointage_type_id for row in transactions(db, account)] == [frais.id, None]


@pytest.mark.parametrize("role", ["DIRECTION", "COMPTABLE"])
def test_roles_without_import_permission_cannot_confirm(client, reference, account, db, role):
    make_auth_user(reference, role, email=f"{role.lower()}@example.com")
    headers = bearer(login(client, f"{role.lower()}@example.com"))

    response = confirm(client, headers, account.id, xlsx(("Relevé", STATEMENT)))

    assert response.status_code == 403
    assert transactions(db, account) == []


# --- Consultation (P7.3) ---------------------------------------------------------------------------


def history(client, headers, company_id: int, **params):
    return client.get(
        "/api/statements", params={"company_id": company_id, **params}, headers=headers
    )


def test_history_lists_the_company_statements_newest_first(client, tresorerie, account, db):
    manual_balance(db, account, "1000000")
    first = confirm(client, tresorerie, account.id, xlsx(("Relevé", STATEMENT))).json()
    second_rows = [HEADER, ["27/09/2026", None, "VIR RECU", None, 1000, 1038349.5]]
    second = confirm(
        client, tresorerie, account.id, xlsx(("Relevé", second_rows)), nom="octobre.xlsx"
    ).json()

    items = history(client, tresorerie, account.company_id).json()

    assert [item["id"] for item in items] == [second["statement_id"], first["statement_id"]]
    oldest = items[1]
    assert oldest | {"importe_le": None, "controle_solde": None} == {
        "id": first["statement_id"],
        "import_id": first["import_id"],
        "fichier_nom": "releve.xlsx",
        "importe_le": None,
        "importe_par": oldest["importe_par"],
        "bank_account_id": account.id,
        "bank_code": "CIH",
        "devise": "MAD",
        "compte_libelle": account.libelle,
        "compte_numero": account.numero,
        "periode_debut": "2026-09-24",
        "periode_fin": "2026-09-26",
        "solde_ouverture": "1000000.00",
        "solde_cloture": "1037349.50",
        "nb_lignes": 3,
        "nb_erreurs": 0,
        "nb_doublons": 0,
        "controle_solde": None,
    }
    assert oldest["importe_par"] is not None
    assert oldest["controle_solde"]["statut"] == "Écart"
    assert items[0]["controle_solde"] is None


def test_history_never_shows_the_other_company(client, tresorerie, account, db):
    confirm(client, tresorerie, account.id, xlsx(("Relevé", STATEMENT)))
    other = db.scalar(select(Company).filter_by(code="SOCX"))

    assert history(client, tresorerie, other.id).json() == []


def test_history_can_be_filtered_by_account(client, tresorerie, account, db):
    confirm(client, tresorerie, account.id, xlsx(("Relevé", STATEMENT)))

    same = history(client, tresorerie, account.company_id, bank_account_id=account.id).json()
    other = history(client, tresorerie, account.company_id, bank_account_id=999999).json()

    assert (len(same), other) == (1, [])


def test_history_of_unknown_company_gives_404(client, tresorerie):
    assert history(client, tresorerie, 999999).status_code == 404


def test_history_needs_a_company(client, tresorerie):
    assert client.get("/api/statements", headers=tresorerie).status_code == 422


def test_statement_transactions_are_listed_in_order(client, tresorerie, account, db):
    rows = [
        ["Date", "Libellé", "Débit", "Crédit", "Pointage"],
        ["25/09/2026", "CHQ N° 1234567", "12 500,50", None, "Décaissement"],
        ["24/09/2026", "VIR RECU", None, 50000, None],
    ]
    body = confirm(client, tresorerie, account.id, xlsx(("Relevé", rows))).json()

    response = client.get(
        f"/api/statements/{body['statement_id']}/transactions", headers=tresorerie
    )

    assert response.status_code == 200
    first, second = response.json()
    assert (first["date_operation"], first["credit"], first["pointage"]) == (
        "2026-09-24",
        "50000.00",
        None,
    )
    assert second | {"id": 0} == {
        "id": 0,
        "societe": "Simtis",
        "pointage": "Décaissement",
        "banque": "CIH",
        "date_operation": "2026-09-25",
        "date_valeur": None,
        "libelle": "CHQ N° 1234567",
        "debit": "12500.50",
        "credit": "0.00",
        "solde": None,
        "lettrage_escompte": None,
        "commentaire": None,
        "reference": "1234567",
        "montant": "-12500.50",
        "statut": "Non rapprochée",
    }
    # Les 11 champs du format standard d'abord, dans leur ordre
    assert list(second)[1:12] == [
        "societe",
        "pointage",
        "banque",
        "date_operation",
        "date_valeur",
        "libelle",
        "debit",
        "credit",
        "solde",
        "lettrage_escompte",
        "commentaire",
    ]


def test_unknown_statement_gives_404(client, tresorerie):
    assert client.get("/api/statements/999999/transactions", headers=tresorerie).status_code == 404


# --- Export au format standard -------------------------------------------------------------------


def export(client, headers, statement_id: int):
    return client.get(f"/api/statements/{statement_id}/export", headers=headers)


def test_export_is_the_standard_statement_in_excel(client, tresorerie, account):
    rows = [
        [
            "Date opération",
            "Date valeur",
            "Libellé",
            "Débit",
            "Crédit",
            "Solde",
            "Pointage",
            "Lettrage",
            "Observation",
        ],
        [
            "24/09/2026",
            "24/09/2026",
            "VIR RECU",
            None,
            50000,
            1050000,
            "encaissement",
            "L-12",
            None,
        ],
        ["25/09/2026", None, "FRAIS", "12,50", None, 1049987.5, "Inconnu", None, "à justifier"],
    ]
    body = confirm(client, tresorerie, account.id, xlsx(("Relevé", rows))).json()

    response = export(client, tresorerie, body["statement_id"])

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert response.headers["content-disposition"] == (
        'attachment; filename="releve_CIH_MAD_2026-09-24_2026-09-25.xlsx"'
    )
    sheet = load_workbook(BytesIO(response.content)).active
    assert sheet.title == "Relevé standard"
    values = [list(row) for row in sheet.iter_rows(values_only=True)]
    assert values[0] == [
        "Société",
        "Pointage",
        "Banque",
        "Date d'opération",
        "Date de valeur",
        "Libellé",
        "Débit",
        "Crédit",
        "Solde",
        "Lettrage / Escompte",
        "Commentaire",
    ]
    assert values[1] == [
        "Simtis",
        "Encaissement",
        "CIH",
        datetime(2026, 9, 24),
        datetime(2026, 9, 24),
        "VIR RECU",
        None,  # débit nul : cellule vide
        50000,
        1050000,
        "L-12",
        None,
    ]
    # Pointage inconnu : vide ; montants en vrais nombres
    assert values[2][:3] == ["Simtis", None, "CIH"]
    assert (values[2][6], values[2][8], values[2][10]) == (12.5, 1049987.5, "à justifier")
    assert sheet["D2"].number_format == "DD/MM/YYYY"
    assert sheet["H2"].number_format == "#,##0.00"


def test_export_of_unknown_statement_gives_404(client, tresorerie):
    assert export(client, tresorerie, 999999).status_code == 404


def test_export_follows_the_reading_permissions(client, reference, tresorerie, account):
    body = confirm(client, tresorerie, account.id, xlsx(("Relevé", STATEMENT))).json()
    make_auth_user(reference, "DIRECTION", email="direction@example.com")
    make_auth_user(reference, email="sans.role@example.com")

    direction = export(client, bearer(login(client, "direction@example.com")), body["statement_id"])
    sans_role = export(client, bearer(login(client, "sans.role@example.com")), body["statement_id"])

    assert (direction.status_code, sans_role.status_code) == (200, 403)


@pytest.mark.parametrize("role", ["COMPTABLE", "DIRECTION"])
def test_statements_are_read_with_reconciliation_view(client, reference, account, role):
    make_auth_user(reference, role, email=f"{role.lower()}@example.com")
    headers = bearer(login(client, f"{role.lower()}@example.com"))

    assert history(client, headers, account.company_id).status_code == 200


def test_user_without_statement_permission_gets_403(client, reference, account):
    make_auth_user(reference, email="sans.role@example.com")
    headers = bearer(login(client, "sans.role@example.com"))

    response = history(client, headers, account.company_id)

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Permission requise : statements.import ou reconciliation.view."
    }


# --- Relevé continu d'un compte --------------------------------------------------------------------

SEPTEMBER = [HEADER, *STATEMENT[4:7]]  # 24, 25 et 26/09, solde 1 000 000 → 1 037 349,50
OCTOBER = [
    HEADER,
    STATEMENT[6],  # 26/09 déjà importé : écarté, pas recopié
    ["01/10/2026", None, "VIR RECU CLIENT DEF", None, 2650.5, 1040000],
]


def continuous(client, headers, account_id, **params):
    return client.get(f"/api/statements/accounts/{account_id}", params=params, headers=headers)


def test_each_import_is_appended_to_the_account_statement(client, tresorerie, account):
    confirm(client, tresorerie, account.id, xlsx(("Relevé", SEPTEMBER)), nom="septembre.xlsx")
    confirm(client, tresorerie, account.id, xlsx(("Relevé", OCTOBER)), nom="octobre.xlsx")

    body = continuous(client, tresorerie, account.id).json()

    assert body | {"operations": None} == {
        "bank_account_id": account.id,
        "societe": "Simtis",
        "bank_code": "CIH",
        "devise": "MAD",
        "compte_libelle": account.libelle,
        "compte_numero": account.numero,
        "periode_debut": "2026-09-24",
        "periode_fin": "2026-10-01",
        "nb_operations": 4,
        "total_debit": "12650.50",
        "total_credit": "52650.50",
        "solde_ouverture": "1000000.00",
        "solde_cloture": "1040000.00",
        "operations": None,
    }
    assert [op["date_operation"] for op in body["operations"]] == [
        "2026-09-24",
        "2026-09-25",
        "2026-09-26",
        "2026-10-01",
    ]
    assert body["operations"][0]["banque"] == "CIH"


def test_account_statement_can_be_limited_to_a_period(client, tresorerie, account):
    confirm(client, tresorerie, account.id, xlsx(("Relevé", SEPTEMBER)))
    confirm(client, tresorerie, account.id, xlsx(("Relevé", OCTOBER)), nom="octobre.xlsx")

    body = continuous(client, tresorerie, account.id, **{"from": "2026-09-25", "to": "2026-09-26"})

    assert [op["libelle"] for op in body.json()["operations"]] == [
        "CHQ N° 1234567 FOURNISSEUR X",
        "FRAIS TENUE DE COMPTE",
    ]
    assert body.json()["solde_ouverture"] == "1050000.00"  # avant le chèque du 25/09
    assert body.json()["solde_cloture"] == "1037349.50"


def test_account_statement_never_mixes_another_account(client, tresorerie, account, db):
    other = save(
        db,
        build_account(
            db.scalar(select(Company).filter_by(code="SIMTIS")),
            db.scalar(select(Bank).filter_by(code="BP")),
            numero="RIB-IMPORT-AUTRE",
        ),
    )
    confirm(client, tresorerie, account.id, xlsx(("Relevé", SEPTEMBER)))

    body = continuous(client, tresorerie, other.id).json()

    assert (body["nb_operations"], body["operations"], body["periode_debut"]) == (0, [], None)
    assert (body["solde_ouverture"], body["solde_cloture"]) == (None, None)


def test_account_statement_errors(client, tresorerie, account):
    reversed_dates = continuous(
        client, tresorerie, account.id, **{"from": "2026-10-02", "to": "2026-10-01"}
    )

    assert continuous(client, tresorerie, 999999).status_code == 404
    assert reversed_dates.status_code == 409


def test_account_statement_export(client, tresorerie, account):
    confirm(client, tresorerie, account.id, xlsx(("Relevé", SEPTEMBER)))
    confirm(client, tresorerie, account.id, xlsx(("Relevé", OCTOBER)), nom="octobre.xlsx")

    response = client.get(f"/api/statements/accounts/{account.id}/export", headers=tresorerie)

    assert response.headers["content-disposition"] == (
        'attachment; filename="releve_CIH_MAD_2026-09-24_2026-10-01.xlsx"'
    )
    values = list(load_workbook(BytesIO(response.content)).active.iter_rows(values_only=True))
    assert values[0][3] == "Date d'opération" and len(values[0]) == 11
    assert [row[3].date() for row in values[1:]] == [
        date(2026, 9, 24),
        date(2026, 9, 25),
        date(2026, 9, 26),
        date(2026, 10, 1),
    ]


def test_empty_account_statement_cannot_be_exported(client, tresorerie, account):
    response = client.get(f"/api/statements/accounts/{account.id}/export", headers=tresorerie)

    assert response.status_code == 409
    assert response.json() == {"detail": "Aucune opération à exporter sur cette période."}


def test_account_statement_follows_the_reading_permissions(client, reference, account):
    make_auth_user(reference, "DIRECTION", email="direction@example.com")
    make_auth_user(reference, email="sans.role@example.com")

    direction = continuous(client, bearer(login(client, "direction@example.com")), account.id)
    sans_role = continuous(client, bearer(login(client, "sans.role@example.com")), account.id)

    assert (direction.status_code, sans_role.status_code) == (200, 403)
