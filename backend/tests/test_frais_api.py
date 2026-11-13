"""Comptabilisation des droits de timbre par SIMTIS (13/10/2026)."""

import csv
import io
import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from openpyxl import Workbook, load_workbook
from sqlalchemy import select

from app.models import (
    AccountingEntry,
    AuditLog,
    Bank,
    BankTransaction,
    FraisLigne,
    ReconciliationMatch,
)
from app.services import frais_service
from app.services.accounting_import_service import EntryLine, _mark_simtis_entries
from app.services.errors import ConflictError
from app.services.frais_service import (
    est_timbre,
    numero_piece,
    regrouper_timbres,
    type_commission,
    type_frais_tva,
    ventilation,
    ventiler_tva,
)
from tests.helpers import bearer, login, make_auth_user
from tests.test_reconciliation_api import account, company, ecriture, operation, statuses

JOUR = date(2026, 4, 23)
VERSEMENT = "DROIT DE TIMBRE SUR VERSEMENT"
REMISE = "DROITS DE TIMBRE SUR REMISE LCN N 2600114"


@pytest.fixture
def comptable(client, reference) -> dict[str, str]:
    make_auth_user(reference, "COMPTABLE", email="comptable@example.com")
    return bearer(login(client, "comptable@example.com"))


@pytest.fixture
def direction(client, reference) -> dict[str, str]:
    make_auth_user(reference, "DIRECTION", email="direction@example.com")
    return bearer(login(client, "direction@example.com"))


def bp(db, compte_timbre: str | None = "61670000"):
    compte = account(db, bank_code="BP")
    compte.journal_sage = "5243,5543"
    compte.journal_frais = "5543"
    compte.compte_comptable = "55410003"
    compte.compte_timbre = compte_timbre
    db.flush()
    return compte


def timbres_du_jour(db, compte, jour=JOUR):
    return [
        operation(db, compte, "-200", jour, REMISE),
        operation(db, compte, "-1", jour, VERSEMENT),
        operation(db, compte, "-1", jour, VERSEMENT),
    ]


class _Lecture:
    """Réponse de `GET /api/frais` réduite à une famille (le tableau unique les mêle)."""

    def __init__(self, status_code: int, data: dict):
        self.status_code = status_code
        self._data = data

    def json(self) -> dict:
        return self._data


def lire(client, headers, db, famille="timbres", **params):
    params = {"company_id": str(company(db).id), "from": "2026-04-01", "to": "2026-04-30", **params}
    response = client.get("/api/frais", params=params, headers=headers)
    if response.status_code != 200 or famille is None:
        return response
    data = response.json()
    return _Lecture(
        200,
        {
            **data,
            "propositions": [p for p in data["propositions"] if p["famille"] == famille],
            "ecritures": [e for e in data["ecritures"] if e["famille"] == famille],
        },
    )


def valider(client, headers, db, *jours, famille="timbres"):
    """`jours` : (compte, jour) pour toutes les écritures du jour, ou (compte, jour, opération)
    pour l'écriture d'un frais (13/11/2026)."""
    body = {
        "company_id": company(db).id,
        "jours": [
            {
                "famille": famille,
                "bank_account_id": choix[0].id,
                "date": str(choix[1]),
                **({"transaction_id": choix[2]} if len(choix) > 2 else {}),
            }
            for choix in jours
        ],
    }
    return client.post("/api/frais/valider", json=body, headers=headers)


def exporter(client, headers, db, famille=None, *, banque="BP", mois="2026-04", premiere=None):
    """Export pour Sage d'une banque et d'un mois (09/11/2026), numéroté à partir de `premiere`
    (par défaut la pièce 001 du mois) ; `famille` est ignorée (un fichier toutes familles)."""
    params = {
        "company_id": str(company(db).id),
        "bank_id": str(db.scalar(select(Bank.id).filter_by(code=banque))),
        "mois": mois,
        "premiere_piece": premiere or f"{banque}{mois[2:4]}{mois[5:7]}001",
    }
    return client.get("/api/frais/export", params=params, headers=headers)


def lignes_csv(response) -> list[tuple[str, ...]]:
    """Lignes du fichier CSV pour Sage (16/10/2026) : point-virgule, Windows-1252."""
    texte = response.content.decode("cp1252")
    return [tuple(row) for row in csv.reader(io.StringIO(texte), delimiter=";")]


def actions(db) -> list[str]:
    return list(db.scalars(select(AuditLog.action).order_by(AuditLog.id)))


# --- Règles pures ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("libelle", "attendu"),
    [
        (VERSEMENT, True),
        (REMISE, True),
        ("droit de timbre sur versement", True),
        ("COMMISSION", False),
        ("TIMBRE FISCAL", False),
        ("REMBOURSEMENT DROIT DE TIMBRE", False),
        (None, False),
    ],
)
def test_a_stamp_duty_is_read_from_the_label(libelle, attendu):
    assert est_timbre(libelle) is attendu


def _tx(id_, compte, jour, montant, libelle=VERSEMENT):
    return BankTransaction(
        id=id_,
        bank_account_id=compte,
        date_operation=jour,
        montant=Decimal(montant),
        libelle=libelle,
    )


def test_one_entry_per_stamp_without_credits_or_amounts_already_in_sage():
    """13/11/2026 : une écriture par frais (plus une par jour) ; Sage bloque un frais du même
    montant, ou toute la journée quand son écriture vaut le total du jour."""
    autre_jour = date(2026, 4, 24)
    jour_total = date(2026, 4, 25)
    pieces = regrouper_timbres(
        [
            _tx(1, 1, JOUR, "-1"),
            _tx(2, 1, JOUR, "-200", REMISE),
            _tx(3, 2, JOUR, "-1"),
            _tx(4, 1, JOUR, "1"),  # remboursement : pas un frais
            _tx(5, 1, JOUR, "-50", "COMMISSION"),
            _tx(6, 1, autre_jour, "-1"),
            _tx(7, 1, autre_jour, "-1"),
            _tx(8, 1, autre_jour, "-20", REMISE),
            _tx(9, 1, jour_total, "-1"),
            _tx(10, 1, jour_total, "-20", REMISE),
        ],
        # Sage : un timbre de 1,00 le 24 (un seul des deux) ; l'écriture du jour (21,00) le 25
        {(1, autre_jour): [Decimal("1.00")], (1, jour_total): [Decimal("21.00")]},
    )

    assert [(p.bank_account_id, p.jour, p.transaction_id, p.total) for p in pieces] == [
        (1, JOUR, 1, Decimal("1")),
        (1, JOUR, 2, Decimal("200")),
        (2, JOUR, 3, Decimal("1")),
        (1, autre_jour, 7, Decimal("1")),
        (1, autre_jour, 8, Decimal("20")),
    ]
    assert [[tx.id for tx in p.operations] for p in pieces[:2]] == [[1], [2]]


# --- Préparer -------------------------------------------------------------------------------------


def test_one_entry_is_proposed_per_fee_and_nothing_is_written(client, comptable, db):
    compte = bp(db)
    timbres_du_jour(db, compte)
    operation(db, compte, "-1", date(2026, 4, 24), VERSEMENT)
    operation(db, compte, "-30", JOUR, "COMMISSION")

    response = lire(client, comptable, db)

    assert response.status_code == 200
    body = response.json()
    # Une écriture par frais (13/11/2026), dans l'ordre du relevé pour un même jour
    assert [(p["date"], p["total"], p["nb_operations"]) for p in body["propositions"]] == [
        ("2026-04-24", "1.00", 1),
        ("2026-04-23", "200.00", 1),
        ("2026-04-23", "1.00", 1),
        ("2026-04-23", "1.00", 1),
    ]
    assert body["propositions"][0]["libelle"] == "DT D'ENREGISTREMENT"
    assert (
        body["propositions"][1]["transaction_id"] == body["propositions"][1]["operations"][0]["id"]
    )
    # Tableau unique : le total compte aussi la COMMISSION de 30 du même jour
    assert body["total_propositions"] == "233.00"
    assert body["ecritures"] == []
    assert db.scalar(select(AccountingEntry).filter_by(origine="SIMTIS")) is None


def test_a_day_already_booked_in_sage_or_a_matched_stamp_is_not_proposed(client, comptable, db):
    compte = bp(db)
    timbres_du_jour(db, compte)
    ecriture(db, compte, "202", JOUR, "DT D'ENREGISTREMENT")
    autre = operation(db, compte, "-1", date(2026, 4, 24), VERSEMENT)
    autre.statut = "Rapprochée"
    db.flush()

    assert lire(client, comptable, db).json()["propositions"] == []


# --- Valider --------------------------------------------------------------------------------------


def test_validating_creates_the_entry_and_matches_it_at_once(client, comptable, db):
    compte = bp(db)
    timbres = timbres_du_jour(db, compte)

    # Le jour sans opération : ses trois écritures (une par frais, 13/11/2026)
    response = valider(client, comptable, db, (compte, JOUR))

    assert response.status_code == 200, response.text
    codes = response.json()["codes"]
    entries = list(
        db.scalars(select(AccountingEntry).filter_by(origine="SIMTIS").order_by(AccountingEntry.id))
    )
    # Pas de N° pièce avant l'export vers Sage (09/11/2026) : l'API rend le code du rapprochement
    assert {(e.journal, e.compte, e.libelle, e.numero_piece) for e in entries} == {
        ("5543", "55410003", "DT D'ENREGISTREMENT", None)
    }
    assert [(e.debit, e.credit, e.montant) for e in entries] == [
        (Decimal("0.00"), Decimal("200.00"), Decimal("200.00")),
        (Decimal("0.00"), Decimal("1.00"), Decimal("1.00")),
        (Decimal("0.00"), Decimal("1.00"), Decimal("1.00")),
    ]
    matches = list(
        db.scalars(
            select(ReconciliationMatch).filter_by(origine="Frais").order_by(ReconciliationMatch.id)
        )
    )
    assert {(m.statut, m.origine, m.type) for m in matches} == {("Validée", "Frais", "1-1")}
    assert statuses(db, *timbres, *entries) == ["Rapprochée"] * 6
    assert actions(db).count("comptabilisation_timbres") == 3

    body = lire(client, comptable, db).json()
    assert body["propositions"] == []
    assert sorted(
        (e["code"], e["numero_piece"], e["nb_operations"], e["exportee_le"])
        for e in body["ecritures"]
    ) == sorted((m.code, None, 1, None) for m in matches)
    assert codes == [m.code for m in matches]


def test_one_fee_is_validated_alone(client, comptable, db):
    """13/11/2026 : l'opération choisie seulement ; les autres frais du jour restent proposés."""
    compte = bp(db)
    remise, versement, _ = timbres_du_jour(db, compte)

    response = valider(client, comptable, db, (compte, JOUR, remise.id))

    assert response.status_code == 200, response.text
    entry = db.scalar(select(AccountingEntry).filter_by(origine="SIMTIS"))
    assert entry.montant == Decimal("200.00")
    assert statuses(db, remise, versement) == ["Rapprochée", "Non rapprochée"]
    restantes = lire(client, comptable, db).json()["propositions"]
    assert [p["total"] for p in restantes] == ["1.00", "1.00"]

    # Déjà comptabilisé : 409, rien n'est écrit
    again = valider(client, comptable, db, (compte, JOUR, remise.id))
    assert again.status_code == 409
    assert "ce frais n'est plus à comptabiliser" in again.json()["detail"]


def test_validation_is_all_or_nothing_and_recomputed_by_the_server(client, comptable, db):
    compte = bp(db)
    timbres_du_jour(db, compte)

    response = valider(client, comptable, db, (compte, JOUR), (compte, date(2026, 4, 25)))

    assert response.status_code == 409
    assert "plus de droits de timbre" in response.json()["detail"]
    assert db.scalar(select(AccountingEntry).filter_by(origine="SIMTIS")) is None


def test_validation_needs_the_bank_account_settings(client, comptable, db):
    compte = bp(db)
    # Deux journaux Sage, aucun en « 55 » (10/11/2026) : lequel ?
    compte.journal_frais = None
    compte.journal_sage = "5243,5143"
    db.flush()
    timbres_du_jour(db, compte)

    response = valider(client, comptable, db, (compte, JOUR))

    assert response.status_code == 409
    assert "journal des frais" in response.json()["detail"]


def test_preparing_needs_the_permission(client, direction, db):
    compte = bp(db)
    timbres_du_jour(db, compte)

    assert lire(client, direction, db).status_code == 200
    assert valider(client, direction, db, (compte, JOUR)).status_code == 403
    assert exporter(client, direction, db).status_code == 403


# --- Export pour Sage ------------------------------------------------------------------------------


def test_export_writes_a_balanced_csv_entry_and_marks_the_entry(client, comptable, db):
    """16/10/2026 : un CSV au point-virgule, Référence vide ; 11/11/2026 : le timbre au débit de
    61671000, la banque au crédit de son compte comptable, Sens « D » / « C »."""
    compte = bp(db, compte_timbre=None)
    timbres_du_jour(db, compte)
    valider(client, comptable, db, (compte, JOUR))

    response = exporter(client, comptable, db, premiere="BP2604045")

    assert response.status_code == 200, response.text
    code = "BP2604045"  # N° donné par le comptable à l'export (09/11/2026)
    assert response.headers["content-type"].startswith("text/csv")
    assert ".csv" in response.headers["content-disposition"]
    rows = lignes_csv(response)
    # Format d'import paramétrable de Sage (15/10/2026), sans ligne d'en-tête (11/11/2026) : la
    # première ligne est déjà une écriture, dans l'ordre des colonnes de Sage
    assert all(len(row) == len(frais_service.COLONNES_SAGE) for row in rows)
    vides = ("",) * 7
    # Une pièce par frais, toutes ses lignes au libellé de l'opération du relevé (13/11/2026)
    assert rows == [
        ("23/04/2026", code, "5543", "61671000", "", REMISE, "200,00", "D") + vides,
        ("23/04/2026", code, "5543", "55410003", "", REMISE, "200,00", "C") + vides,
        ("23/04/2026", "BP2604046", "5543", "61671000", "", VERSEMENT, "1,00", "D") + vides,
        ("23/04/2026", "BP2604046", "5543", "55410003", "", VERSEMENT, "1,00", "C") + vides,
        ("23/04/2026", "BP2604047", "5543", "61671000", "", VERSEMENT, "1,00", "D") + vides,
        ("23/04/2026", "BP2604047", "5543", "55410003", "", VERSEMENT, "1,00", "C") + vides,
    ]
    entries = list(
        db.scalars(select(AccountingEntry).filter_by(origine="SIMTIS").order_by(AccountingEntry.id))
    )
    for entry in entries:
        db.refresh(entry)
    assert [(e.numero_piece, e.exportee_le is not None) for e in entries] == [
        (code, True),
        ("BP2604046", True),
        ("BP2604047", True),
    ]
    # Une écriture ne s'exporte qu'une fois (09/11/2026)
    again = exporter(client, comptable, db)
    assert again.status_code == 409
    assert "Aucune écriture de frais BP à exporter en 04/2026" in again.json()["detail"]


# --- Suppression et annulation ---------------------------------------------------------------------


def _supprimer(client, headers, entry_id, motif="Erreur de saisie"):
    return client.request(
        "DELETE", f"/api/frais/ecritures/{entry_id}", json={"motif": motif}, headers=headers
    )


def test_an_entry_not_yet_exported_can_be_deleted(client, comptable, db):
    compte = bp(db)
    timbres = timbres_du_jour(db, compte)
    valider(client, comptable, db, (compte, JOUR))
    entry_id = db.scalar(
        select(AccountingEntry.id).filter_by(origine="SIMTIS").order_by(AccountingEntry.id)
    )

    assert _supprimer(client, comptable, entry_id, motif=" ").status_code == 409
    response = _supprimer(client, comptable, entry_id)

    assert response.status_code == 204
    db.expire_all()
    assert db.get(AccountingEntry, entry_id) is None
    # Une écriture par frais (13/11/2026) : seule l'opération de l'écriture supprimée revient
    assert statuses(db, *timbres) == ["Non rapprochée", "Rapprochée", "Rapprochée"]
    assert "suppression_ecriture_frais" in actions(db)
    assert len(lire(client, comptable, db).json()["propositions"]) == 1


def test_an_exported_entry_cannot_be_deleted_nor_cancelled(client, comptable, db):
    compte = bp(db)
    timbres_du_jour(db, compte)
    valider(client, comptable, db, (compte, JOUR))
    match = db.scalar(select(ReconciliationMatch).filter_by(origine="Frais"))
    entry_id = db.scalar(select(AccountingEntry.id).filter_by(origine="SIMTIS"))

    annulation = client.request(
        "DELETE",
        f"/api/reconciliation/matches/{match.id}",
        json={"motif": "test"},
        headers=comptable,
    )
    assert annulation.status_code == 409
    assert "comptabilisée par SIMTIS" in annulation.json()["detail"]

    exporter(client, comptable, db)
    response = _supprimer(client, comptable, entry_id)

    assert response.status_code == 409
    assert "déjà été exportée" in response.json()["detail"]


# --- Retour par l'export Sage ---------------------------------------------------------------------


def test_a_simtis_entry_coming_back_from_sage_is_a_duplicate(client, comptable, db):
    compte = bp(db)
    timbres_du_jour(db, compte)
    valider(client, comptable, db, (compte, JOUR))
    assert exporter(client, comptable, db).status_code == 200
    code = f"BP{JOUR:%y%m}001"

    def ligne(numero, libelle, montant="200.00", piece=None):
        return EntryLine(
            numero=numero,
            statut="Valide",
            motifs=[],
            date_ecriture=JOUR,
            libelle=libelle,
            montant=Decimal(montant),
            numero_piece=piece,
            bank_account_id=compte.id,
        )

    par_libelle = ligne(2, "DT D'ENREGISTREMENT")
    autre_montant = ligne(3, "DT D'ENREGISTREMENT", "15.00")
    _mark_simtis_entries(db, company(db).id, [par_libelle, autre_montant])
    assert par_libelle.statut == "Doublon"
    assert code in par_libelle.motifs[0]
    assert autre_montant.statut == "Valide"

    par_piece = ligne(4, "FRAIS DIVERS", piece=code.lower())
    _mark_simtis_entries(db, company(db).id, [par_piece])
    assert par_piece.statut == "Doublon"

    # Une écriture par frais (13/11/2026) : ses lignes reviennent au libellé du relevé
    par_releve = ligne(5, VERSEMENT.lower(), "1.00")
    autre_libelle = ligne(6, "VIREMENT", "1.00")
    _mark_simtis_entries(db, company(db).id, [par_releve, autre_libelle])
    assert par_releve.statut == "Doublon"
    assert autre_libelle.statut == "Valide"


# --- Frais importés deux fois dans Sage (10/11/2026) -----------------------------------------------

GL_HEADER = ["Date", "Journal", "Compte", "N° pièce", "Libellé", "Débit", "Crédit"]


def grand_livre(*rows) -> bytes:
    workbook = Workbook()
    workbook.active.append(GL_HEADER)
    for row in rows:
        workbook.active.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def analyse_gl(client, headers, db, content: bytes, path: str = "analyse", **form):
    return client.post(
        f"/api/accounting/import/{path}",
        data={"company_id": str(company(db).id), **form},
        files={"fichier": ("gl.xlsx", content, "application/octet-stream")},
        headers=headers,
    )


def frais_exporte(client, comptable, db):
    """Un droit de timbre comptabilisé par SIMTIS et exporté : pièce BP2604001, crédit 202,00
    (une écriture par frais, 13/11/2026)."""
    compte = bp(db)
    operation(db, compte, "-202", JOUR, REMISE)
    valider(client, comptable, db, (compte, JOUR))
    assert exporter(client, comptable, db).status_code == 200
    return compte


def test_a_fee_imported_twice_in_sage_is_flagged_and_its_copy_unchecked(client, comptable, db):
    frais_exporte(client, comptable, db)
    ligne_frais = [JOUR, "5543", "55410003", "BP2604001", "DT D'ENREGISTREMENT", None, 202]
    content = grand_livre(ligne_frais, ligne_frais, ligne_frais)

    body = analyse_gl(client, comptable, db, content).json()

    lignes = body["lignes"]
    assert [line["statut"] for line in lignes] == ["Doublon", "Valide", "Valide"]
    assert [line["piece_repetee"] for line in lignes] == [False, True, True]
    assert "Déjà comptabilisée par SIMTIS (pièce BP2604001)" in lignes[0]["motifs"][0]
    assert "BP2604001 répété à l'identique" in lignes[1]["motifs"][0]
    assert body["pieces_repetees"] == [
        {
            "numero_piece": "BP2604001",
            "bank_account_id": lignes[0]["bank_account_id"],
            "bank_code": "BP",
            "date_ecriture": JOUR.isoformat(),
            "montant": lignes[0]["montant"],
            "nb": 3,
            "copies": [3, 4],
        }
    ]


def test_a_rechecked_copy_is_imported(client, comptable, db):
    frais_exporte(client, comptable, db)
    ligne_frais = [JOUR, "5543", "55410003", "BP2604001", "DT D'ENREGISTREMENT", None, 202]
    content = grand_livre(ligne_frais, ligne_frais)

    body = analyse_gl(
        client, comptable, db, content, path="confirm", lignes_choisies=json.dumps([3])
    ).json()

    assert body["nb_importees"] == 1


@pytest.mark.parametrize(
    "rows",
    [
        # Même N° pièce SIMTIS, montants différents : pas une copie
        [
            [JOUR, "5543", "55410003", "BP2604001", "DT D'ENREGISTREMENT", None, 202],
            [JOUR, "5543", "55410003", "BP2604001", "DT D'ENREGISTREMENT", None, 15],
        ],
        # Même N° pièce SIMTIS, libellés différents
        [
            [JOUR, "5543", "55410003", "BP2604001", "DT D'ENREGISTREMENT", None, 202],
            [JOUR, "5543", "55410003", "BP2604001", "COM VIR", None, 202],
        ],
        # Pièce Sage ordinaire répétée à l'identique : jamais signalée
        [
            [JOUR, "5543", "55410003", "P9", "AGIOS", None, 50],
            [JOUR, "5543", "55410003", "P9", "AGIOS", None, 50],
        ],
    ],
)
def test_only_identical_copies_of_a_simtis_piece_are_flagged(client, comptable, db, rows):
    frais_exporte(client, comptable, db)

    body = analyse_gl(client, comptable, db, grand_livre(*rows)).json()

    assert body["pieces_repetees"] == []
    assert not any(line["piece_repetee"] for line in body["lignes"])


def test_a_repeated_piece_of_a_fee_not_yet_exported_is_not_flagged(client, comptable, db):
    """Sans export, le frais n'a pas de N° pièce : il ne peut pas être en double dans Sage."""
    compte = bp(db)
    timbres_du_jour(db, compte)
    valider(client, comptable, db, (compte, JOUR))
    ligne_frais = [JOUR, "5543", "55410003", "BP2604001", "DT D'ENREGISTREMENT", None, 202]

    body = analyse_gl(client, comptable, db, grand_livre(ligne_frais, ligne_frais)).json()

    assert body["pieces_repetees"] == []


def test_validated_entries_are_listed_with_their_code(db, comptable, client):
    compte = bp(db)
    timbres_du_jour(db, compte)
    valider(client, comptable, db, (compte, JOUR))

    items = frais_service.ecritures(db, company(db).id)

    assert [(item.bank_code, item.nb_operations) for item in items] == [("BP", 1)] * 3


def test_the_reconciliation_screens_show_a_fees_match(client, comptable, db):
    """Une correspondance d'origine « Frais » se lit dans les volets et l'historique."""
    compte = bp(db)
    timbres_du_jour(db, compte)
    valider(client, comptable, db, (compte, JOUR))
    params = {"company_id": str(company(db).id), "du": "2026-04-01", "au": "2026-04-30"}

    for path in ("transactions", "history"):
        response = client.get(f"/api/reconciliation/{path}", params=params, headers=comptable)
        assert response.status_code == 200, (path, response.text)


# --- Commissions (13/10/2026) ---------------------------------------------------------------------

COM_EFFET = "COMMISSION EFFET N 3600839 REMIS PAR SGMB EN FAVEUR DE X"
TVA_EFFET = "TVA COM EFFET N 3600839 REMIS PAR SGMB EN FAVEUR DE X"


@pytest.mark.parametrize(
    ("libelle", "attendu"),
    [
        ("COMMISSION", "commission"),
        (" commission ", "commission"),
        ("TAXE SUR VALEUR AJOUTEE", "tva"),
        (COM_EFFET, "commission_effet"),
        (TVA_EFFET, "tva_commission_effet"),
        # Restent manuels
        # TVA comprise, dans la COM du jour depuis le 14/10/2026
        ("COMMISSION VIR. RTGS EMIS VERS BMCE EN FAVEUR DE X", "commission_rtgs"),
        ("COMMISSION REGLEMENT PRELEVEMENT EN FAVEUR DE X", "commission_prelevement"),
        ("COMMISSION COTISATIONS CNSS", None),
        ("TVA COM VIR. RTGS", None),
        (VERSEMENT, None),
    ],
)
def test_only_the_four_commission_labels_are_taken(libelle, attendu):
    assert type_commission(libelle) == attendu


def commissions(db, compte_tva: str | None = "34552000"):
    compte = bp(db)
    compte.compte_commission = "61470000"
    compte.compte_commission_effet = "61471000"
    compte.compte_tva = compte_tva
    db.flush()
    lignes = [
        operation(db, compte, "-20", JOUR, "COMMISSION"),
        operation(db, compte, "-30", JOUR, "COMMISSION"),
        # La TVA de chaque commission : 10 % de 20 et de 30 (09/11/2026)
        operation(db, compte, "-2", JOUR, "TAXE SUR VALEUR AJOUTEE"),
        operation(db, compte, "-3", JOUR, "TAXE SUR VALEUR AJOUTEE"),
        operation(db, compte, "-10", JOUR, COM_EFFET),
        operation(db, compte, "-1", JOUR, TVA_EFFET),
        operation(db, compte, "-165", JOUR, "COMMISSION COTISATIONS CNSS"),
    ]
    return compte, lignes


def test_one_com_entry_per_commission_and_per_vat_line(client, comptable, db):
    """13/11/2026 : une écriture par opération ; une commission et sa TVA sur deux lignes du
    relevé font deux écritures."""
    commissions(db)

    body = lire(client, comptable, db, "commissions").json()

    assert [
        (p["libelle"], p["total"], p["nb_operations"], [d["type"] for d in p["details"]])
        for p in body["propositions"]
    ] == [
        ("COM", "20.00", 1, ["commission"]),
        ("COM", "30.00", 1, ["commission"]),
        ("COM", "2.00", 1, ["tva"]),
        ("COM", "3.00", 1, ["tva"]),
        ("COM", "10.00", 1, ["commission_effet"]),
        ("COM", "1.00", 1, ["tva_commission_effet"]),
    ]
    # Les timbres ne voient pas les commissions
    assert lire(client, comptable, db).json()["propositions"] == []


def test_a_day_with_a_sage_com_entry_is_not_proposed(client, comptable, db):
    """Une écriture Sage « COM » du total du jour (passée avant le 13/11/2026) couvre tous ses
    frais."""
    compte, _ = commissions(db)
    ecriture(db, compte, "66", JOUR, "COM")

    assert lire(client, comptable, db, "commissions").json()["propositions"] == []


def test_a_sage_com_entry_blocks_only_the_fee_of_its_amount(client, comptable, db):
    """13/11/2026 : une écriture Sage « COM » d'un autre montant que le total du jour ne couvre
    que le frais du même montant ; d'un montant sans frais, elle ne bloque rien."""
    compte, _ = commissions(db)
    ecriture(db, compte, "30", JOUR, "COM")
    ecriture(db, compte, "231", JOUR, "COM")

    totaux = [p["total"] for p in lire(client, comptable, db, "commissions").json()["propositions"]]

    assert totaux == ["20.00", "2.00", "3.00", "10.00", "1.00"]


def test_validating_commissions_matches_them_and_export_is_balanced(client, comptable, db):
    compte, lignes = commissions(db)

    response = valider(client, comptable, db, (compte, JOUR), famille="commissions")

    assert response.status_code == 200, response.text
    entries = list(
        db.scalars(
            select(AccountingEntry)
            .filter_by(origine="SIMTIS", libelle="COM")
            .order_by(AccountingEntry.id)
        )
    )
    assert [(e.montant, e.numero_piece) for e in entries] == [
        (Decimal(m), None) for m in ("20.00", "30.00", "2.00", "3.00", "10.00", "1.00")
    ]
    assert statuses(db, *lignes) == ["Rapprochée"] * 6 + ["Non rapprochée"]
    assert "comptabilisation_commissions" in actions(db)
    # Les écritures de timbres ne listent pas la COM
    assert lire(client, comptable, db).json()["ecritures"] == []

    export = exporter(client, comptable, db, "commissions")
    assert export.status_code == 200, export.text
    rows = lignes_csv(export)
    # Une pièce par opération, la charge (ou la TVA) au débit et la banque au crédit, toutes deux
    # au libellé du relevé (13/11/2026)
    tva = "TAXE SUR VALEUR AJOUTEE"
    assert [(r[3], r[1], r[5], r[7], r[6]) for r in rows] == [
        ("61473000", "BP2604001", "COMMISSION", "D", "20,00"),
        ("55410003", "BP2604001", "COMMISSION", "C", "20,00"),
        ("61473000", "BP2604002", "COMMISSION", "D", "30,00"),
        ("55410003", "BP2604002", "COMMISSION", "C", "30,00"),
        ("34552142", "BP2604003", tva, "D", "2,00"),
        ("55410003", "BP2604003", tva, "C", "2,00"),
        ("34552142", "BP2604004", tva, "D", "3,00"),
        ("55410003", "BP2604004", tva, "C", "3,00"),
        ("61473000", "BP2604005", COM_EFFET[:50], "D", "10,00"),
        ("55410003", "BP2604005", COM_EFFET[:50], "C", "10,00"),
        ("34552142", "BP2604006", TVA_EFFET[:50], "D", "1,00"),
        ("55410003", "BP2604006", TVA_EFFET[:50], "C", "1,00"),
    ]


def test_a_simtis_com_entry_coming_back_from_sage_is_a_duplicate(client, comptable, db):
    compte, _ = commissions(db)
    valider(client, comptable, db, (compte, JOUR), famille="commissions")
    line = EntryLine(
        numero=2,
        statut="Valide",
        motifs=[],
        date_ecriture=JOUR,
        libelle="COM",
        montant=Decimal("20.00"),
        bank_account_id=compte.id,
    )

    _mark_simtis_entries(db, company(db).id, [line])

    assert line.statut == "Doublon"


def test_an_unknown_family_is_refused(client, comptable, db):
    compte = bp(db)
    assert valider(client, comptable, db, (compte, JOUR), famille="agios").status_code == 422


# --- Format du grand livre, export unique (13/10/2026) --------------------------------------------


def test_lines_follow_the_general_ledger_one_entry_per_fee(client, comptable, db):
    """13/11/2026 : une écriture par frais, toutes ses lignes au libellé du relevé."""
    compte, _ = commissions(db)
    timbres_du_jour(db, compte)

    tableau = lire(client, comptable, db, None).json()

    # Un seul tableau : pour un même jour, les timbres puis la COM, dans l'ordre du relevé
    assert [p["famille"] for p in tableau["propositions"]] == ["timbres"] * 3 + ["commissions"] * 6
    timbre, com, tva = (tableau["propositions"][i] for i in (0, 3, 5))
    assert com["journal"] == "5543"

    def lignes(proposition):
        return [
            (ligne["type"], ligne["compte"], ligne["libelle"], ligne["debit"], ligne["credit"])
            for ligne in proposition["lignes"]
        ]

    assert lignes(com) == [
        ("commission", "61473000", "COMMISSION", "20.00", None),
        (None, "55410003", "COMMISSION", None, "20.00"),
    ]
    assert lignes(tva) == [
        ("tva", "34552142", "TAXE SUR VALEUR AJOUTEE", "2.00", None),
        (None, "55410003", "TAXE SUR VALEUR AJOUTEE", None, "2.00"),
    ]
    assert [
        (ligne["type"], ligne["libelle"], ligne["debit"], ligne["credit"])
        for ligne in timbre["lignes"]
    ] == [
        ("timbre", REMISE, "200.00", None),
        (None, REMISE, None, "200.00"),
    ]

    # Les deux familles se valident ensemble, toutes ou aucune
    body = {
        "company_id": company(db).id,
        "jours": [
            {"famille": "timbres", "bank_account_id": compte.id, "date": str(JOUR)},
            {"famille": "commissions", "bank_account_id": compte.id, "date": str(JOUR)},
        ],
    }
    response = client.post("/api/frais/valider", json=body, headers=comptable)
    assert response.status_code == 200, response.text
    assert response.json()["nb_ecritures"] == 9
    ecrites = lire(client, comptable, db, None).json()["ecritures"]
    assert sorted(e["famille"] for e in ecrites) == ["commissions"] * 6 + ["timbres"] * 3
    com_ecrite = next(
        e for e in ecrites if e["famille"] == "commissions" and e["montant"] == "20.00"
    )
    assert [(ligne["type"], ligne["libelle"]) for ligne in com_ecrite["lignes"]] == [
        ("commission", "COMMISSION"),
        (None, "COMMISSION"),
    ]


def test_one_export_file_holds_stamps_and_commissions(client, comptable, db):
    compte, _ = commissions(db)
    timbres_du_jour(db, compte, date(2026, 4, 22))
    valider(client, comptable, db, (compte, JOUR), famille="commissions")
    valider(client, comptable, db, (compte, date(2026, 4, 22)))

    response = exporter(client, comptable, db)

    assert response.status_code == 200, response.text
    rows = lignes_csv(response)
    tva = "TAXE SUR VALEUR AJOUTEE"
    # Une pièce par frais, ses deux lignes au libellé du relevé (13/11/2026)
    assert [(r[1], r[5], r[7]) for r in rows] == [
        (f"BP2604{n:03d}", libelle, sens)
        for n, libelle in enumerate(
            (REMISE, VERSEMENT, VERSEMENT, "COMMISSION", "COMMISSION", tva, tva)
            + (COM_EFFET[:50], TVA_EFFET[:50]),
            start=1,
        )
        for sens in ("D", "C")
    ]
    montants = [(Decimal(r[6].replace(",", ".")), r[7]) for r in rows]
    assert sum(m for m, sens in montants if sens == "D") == 268
    assert sum(m for m, sens in montants if sens == "C") == 268
    assert exporter(client, comptable, db).status_code == 409


# --- Comptabilisation manuelle (13/10/2026) ------------------------------------------------------


@pytest.mark.parametrize(
    ("total", "taux", "ht", "tva"),
    [
        ("165.00", "10", "150.00", "15.00"),
        ("11.00", "10", "10.00", "1.00"),
        ("100.00", "10", "90.91", "9.09"),
        ("0.05", "20", "0.04", "0.01"),
    ],
)
def test_vat_is_split_from_the_total_and_always_adds_up(total, taux, ht, tva):
    resultat = ventiler_tva(Decimal(total), Decimal(taux))

    assert resultat == (Decimal(ht), Decimal(tva))
    assert sum(resultat) == Decimal(total)


# Un frais qui reste à passer à la main (la RTGS est automatique depuis le 14/10/2026)
RTGS = "FRAIS DE TENUE DE COMPTE"


def manuelle(client, headers, db, operations, **over):
    body = {
        "company_id": company(db).id,
        "transaction_ids": [tx.id for tx in operations],
        "libelle": "COM RTGS",
        **over,
    }
    return client.post("/api/frais/manuelle", json=body, headers=headers)


def test_other_fees_are_listed_apart_from_the_automatic_ones(client, comptable, db):
    compte = bp(db)
    timbres_du_jour(db, compte)
    rtgs = operation(db, compte, "-165", JOUR, RTGS)
    agios = operation(db, compte, "-604.71", JOUR, "AGIOS BANCAIRES")

    body = lire(client, comptable, db, None).json()

    assert {item["id"] for item in body["autres_frais"]} == {rtgs.id, agios.id}


def test_an_automatic_fee_is_never_booked_by_hand(client, comptable, db):
    """Commission déjà dans Sage : elle n'est pas proposée en automatique, mais elle ne se passe pas
    non plus à la main."""
    compte = bp(db)
    commission = operation(db, compte, "-20", JOUR, "COMMISSION")
    # La COM de Sage du même montant (13/11/2026), déjà rapprochée ailleurs : pas « inclus »
    ecriture(db, compte, "20", JOUR, "COM", statut="Rapprochée")

    body = lire(client, comptable, db, None).json()
    response = manuelle(client, comptable, db, [commission])

    assert body["propositions"] == [] and body["autres_frais"] == []
    assert response.status_code == 409
    assert "automatique" in response.json()["detail"]


def test_a_manual_entry_with_vat_is_matched_and_exported_on_two_lines(client, comptable, db):
    compte = bp(db)
    rtgs = operation(db, compte, "-165", JOUR, RTGS)

    response = manuelle(client, comptable, db, [rtgs], taux_tva="10")

    assert response.status_code == 200, response.text
    code = f"BP{JOUR:%y%m}001"  # N° pièce donné à l'export
    entry = db.scalar(select(AccountingEntry).filter_by(famille_frais="manuelle"))
    assert (
        entry.libelle,
        entry.montant,
        entry.montant_tva,
        entry.taux_tva,
        entry.date_ecriture,
    ) == (
        "COM RTGS",
        Decimal("165.00"),
        Decimal("15.00"),
        Decimal("10.00"),
        JOUR,
    )
    assert statuses(db, rtgs) == ["Rapprochée"]
    assert "comptabilisation_manuelle" in actions(db)
    ecrite = next(
        e
        for e in lire(client, comptable, db, None).json()["ecritures"]
        if e["famille"] == "manuelle"
    )
    assert [
        (ligne["type_libelle"], ligne["debit"], ligne["credit"]) for ligne in ecrite["lignes"]
    ] == [
        ("Frais", "150.00", None),
        ("TVA", "15.00", None),
        ("Banque", None, "165.00"),
    ]

    rows = lignes_csv(exporter(client, comptable, db))
    assert [(r[1], r[3], r[5], r[7], r[6]) for r in rows] == [
        (code, "61473000", "COM RTGS", "D", "150,00"),
        (code, "34552142", "TVA COM RTGS", "D", "15,00"),
        (code, "55410003", "COM RTGS", "C", "165,00"),
    ]


def test_a_manual_entry_without_vat_has_one_line_and_a_refund_goes_to_the_debit(
    client, comptable, db
):
    compte = bp(db)
    remboursement = operation(db, compte, "151110.79", JOUR, "AGIOS BANCAIRES")

    response = manuelle(client, comptable, db, [remboursement], libelle="agios  rembourses")

    assert response.status_code == 200, response.text
    entry = db.scalar(select(AccountingEntry).filter_by(famille_frais="manuelle"))
    assert (entry.libelle, entry.debit, entry.credit, entry.montant) == (
        "AGIOS REMBOURSES",
        Decimal("151110.79"),
        Decimal("0.00"),
        Decimal("-151110.79"),
    )
    ecrite = lire(client, comptable, db, None).json()["ecritures"][0]
    assert [(ligne["compte"], ligne["debit"], ligne["credit"]) for ligne in ecrite["lignes"]] == [
        ("63112000", None, "151110.79"),
        ("55410003", "151110.79", None),
    ]
    # Sage : montant positif ; un remboursement d'agios BP au crédit de 63112000, la banque au
    # débit (11/11/2026)
    rows = lignes_csv(exporter(client, comptable, db))
    assert [(r[3], r[5], r[6], r[7]) for r in rows] == [
        ("63112000", "AGIOS REMBOURSES", "151110,79", "C"),
        ("55410003", "AGIOS REMBOURSES", "151110,79", "D"),
    ]


def test_fees_of_a_currency_account_are_not_exported_yet(client, comptable, db):
    compte = bp(db)
    timbres_du_jour(db, compte)
    valider(client, comptable, db, (compte, JOUR))
    compte.devise = "EUR"
    db.flush()

    response = exporter(client, comptable, db)

    assert response.status_code == 409
    assert "BP EUR" in response.json()["detail"]
    assert db.scalar(select(AccountingEntry).filter_by(origine="SIMTIS")).exportee_le is None


def test_a_manual_vat_amount_is_kept_and_must_stay_below_the_total(client, comptable, db):
    compte = bp(db)
    rtgs = operation(db, compte, "-165", JOUR, RTGS)

    trop = manuelle(client, comptable, db, [rtgs], montant_tva="165.00")
    ok = manuelle(client, comptable, db, [rtgs], montant_tva="14.99")

    assert trop.status_code == 409
    assert "inférieure au total" in trop.json()["detail"]
    assert ok.status_code == 200, ok.text
    entry = db.scalar(select(AccountingEntry).filter_by(famille_frais="manuelle"))
    assert (entry.montant_tva, entry.taux_tva) == (Decimal("14.99"), None)


def test_a_manual_entry_needs_one_account_free_fees_a_label_and_a_valid_date(client, comptable, db):
    compte = bp(db)
    autre = account(db, bank_code="AWB")
    autre.journal_sage = "BQ9"
    autre.compte_comptable = "5141"
    db.flush()
    rtgs = operation(db, compte, "-165", JOUR, RTGS)
    ailleurs = operation(db, autre, "-50", JOUR, "AGIOS BANCAIRES")
    rapprochee = operation(db, compte, "-30", JOUR, "AGIOS BANCAIRES")
    rapprochee.statut = "Rapprochée"
    virement = operation(db, compte, "-500", JOUR, "VIR CLIENT ATLAS")
    db.flush()

    assert "même compte" in manuelle(client, comptable, db, [rtgs, ailleurs]).json()["detail"]
    for operations in ([rapprochee], [virement]):
        assert (
            "plus à comptabiliser" in manuelle(client, comptable, db, operations).json()["detail"]
        )
    assert manuelle(client, comptable, db, [rtgs], libelle="   ").status_code == 409
    assert "date" in manuelle(client, comptable, db, [rtgs], date="2026-04-01").json()["detail"]
    assert db.scalar(select(AccountingEntry).filter_by(famille_frais="manuelle")) is None


def test_a_manual_entry_can_be_deleted_before_export(client, comptable, db):
    compte = bp(db)
    rtgs = operation(db, compte, "-165", JOUR, RTGS)
    manuelle(client, comptable, db, [rtgs])
    entry_id = db.scalar(select(AccountingEntry.id).filter_by(famille_frais="manuelle"))

    response = _supprimer(client, comptable, entry_id)

    assert response.status_code == 204
    assert statuses(db, rtgs) == ["Non rapprochée"]


def test_manual_booking_needs_the_permission(client, direction, db):
    compte = bp(db)
    rtgs = operation(db, compte, "-165", JOUR, RTGS)

    assert manuelle(client, direction, db, [rtgs]).status_code == 403


# --- Comptes de charge des frais (05/11/2026) ----------------------------------------------------


@pytest.mark.parametrize(
    ("libelle", "banque", "attendu"),
    [
        ("INTERET CREDOC", "BP", "63110001"),
        ("Intérêts crédoc mars", "BP", "63110001"),
        ("INTERET RELANCE", "AWB", "63110002"),
        ("INTERET CMT / OXYGENE", "BP", "63110004"),
        ("INTERET CMT", "BP", "63119700"),
        ("INTERETS CMT FEVRIER", "AWB", "63119700"),
        ("INTERET DE RETARD/ OP FINANCIERE", "CIH", "63115200"),
        ("INTERET CREDIT ENLEVEMENT", "BP", "63118000"),
        ("INTERET CRED SPOT", "BMCE", "63119400"),
        ("INTERET ACNE/MCNE", "BP", "63119410"),
        ("INTERETS CREDIT AFFACTURAGE", "BP", "63119420"),
        ("INTERETS CMT BP 10.728 KMAD", "BP", "63119710"),
        # Réservé à BP : ailleurs, l'intitulé plus court « INTERET CMT »
        ("INTERETS CMT BP 10.728 KMAD", "AWB", "63119700"),
        ("INTERETS EMPRUNTS GROUPE", "BP", "63119800"),
        ("COMPTE D'ATTENTE / INTERETS", "BP", "63119901"),
        ("CHARGES D'INTERET EXER ANTERIEURS", "BP", "63180000"),
        ("FRAIS D'ESCOMPTE", "BP", "63117000"),
        ("FRAIS DE REFINANCEMENT", "BP", "63119500"),
        # Inchangés : AGIOS selon la banque, COM, sinon les frais bancaires
        ("AGIOS BP", "BMCE", "63111000"),
        ("COM RTGS", "BP", "61473000"),
        ("INTERETS DEBITEURS", "BP", "61473000"),
        ("INTERET CREDOCX", "BP", "61473000"),
    ],
)
def test_a_manual_entry_goes_to_the_account_named_by_its_label(libelle, banque, attendu):
    assert frais_service.compte_charge("frais", libelle, banque) == attendu
    # La TVA reste sur son compte
    assert frais_service.compte_charge("tva", libelle, banque) == "34552142"


def test_the_fee_accounts_are_listed_with_their_reserved_bank(client, direction):
    response = client.get("/api/frais/comptes", headers=direction)

    assert response.status_code == 200
    comptes = {c["numero"]: c for c in response.json()}
    assert len(comptes) == 21
    # Les commissions vont au 61473000 depuis le 11/11/2026 : 61714000 n'est plus dans la liste
    assert "61714000" not in comptes
    assert comptes["63119400"] == {
        "numero": "63119400",
        "intitule": "INTERET CRED SPOT",
        "banque": None,
    }
    assert comptes["63119710"]["banque"] == "BP"
    assert "63119710" not in dict(frais_service.comptes_frais("AWB"))
    assert "63119710" in dict(frais_service.comptes_frais("BP"))


def test_a_manual_entry_takes_the_account_chosen_in_the_list(client, comptable, db):
    compte = bp(db)
    frais = operation(db, compte, "-165", JOUR, RTGS)

    response = manuelle(
        client, comptable, db, [frais], libelle="INTERETS", compte="63119400", taux_tva="10"
    )

    assert response.status_code == 200, response.text
    code = f"BP{JOUR:%y%m}001"  # N° pièce donné à l'export
    ecrite = lire(client, comptable, db, None).json()["ecritures"][0]
    assert [(ligne["compte"], ligne["debit"]) for ligne in ecrite["lignes"]] == [
        ("63119400", "150.00"),
        ("34552142", "15.00"),
        ("55410003", None),
    ]
    rows = lignes_csv(exporter(client, comptable, db))
    assert [(r[1], r[3], r[5], r[6], r[7]) for r in rows] == [
        (code, "63119400", "INTERETS", "150,00", "D"),
        (code, "34552142", "TVA INTERETS", "15,00", "D"),
        (code, "55410003", "INTERETS", "165,00", "C"),
    ]
    # Lignes saisies sans la banque, au débit (11/11/2026)
    saisies = db.scalars(select(FraisLigne).order_by(FraisLigne.ordre)).all()
    assert [(ligne.compte, ligne.sens) for ligne in saisies] == [
        ("63119400", "Débit"),
        ("34552142", "Débit"),
    ]
    audit = db.scalar(select(AuditLog).filter_by(action="comptabilisation_manuelle"))
    assert audit.nouvelle_valeur["compte_charge"] == "63119400"


def test_the_account_of_the_label_needs_no_saved_lines(client, comptable, db):
    compte = bp(db)
    frais = operation(db, compte, "-165", JOUR, RTGS)

    response = manuelle(client, comptable, db, [frais], libelle="INTERET CREDOC", compte="63110001")

    assert response.status_code == 200, response.text
    ecrite = lire(client, comptable, db, None).json()["ecritures"][0]
    assert ecrite["modifiee"] is False
    assert [ligne["compte"] for ligne in ecrite["lignes"]] == ["63110001", "55410003"]


@pytest.mark.parametrize("compte_choisi", ["12a", "123", "1234 5678", "123456789012345678901"])
def test_a_manual_entry_refuses_a_malformed_account(client, comptable, db, compte_choisi):
    """« Autre » (07/11/2026) : 4 à 20 chiffres ; un compte réservé à une autre banque reste
    refusé."""
    compte = account(db, bank_code="AWB")
    compte.journal_sage = "5241"
    compte.journal_frais = "5241"
    compte.compte_comptable = "55410001"
    db.flush()
    frais = operation(db, compte, "-165", JOUR, RTGS)

    response = manuelle(client, comptable, db, [frais], compte=compte_choisi)
    reserve = manuelle(client, comptable, db, [frais], compte="63119710")

    assert response.status_code in (409, 422)
    assert reserve.status_code == 409
    assert "AWB" in reserve.json()["detail"]
    assert statuses(db, frais) == ["Non rapprochée"]


def test_a_manual_entry_takes_an_account_typed_by_hand(client, comptable, db):
    """« Autre » (07/11/2026) : un compte hors liste, saisi à la main, est accepté ; la TVA reste
    sur 34552142 et l'audit le signale."""
    compte = bp(db)
    frais = operation(db, compte, "-165", JOUR, RTGS)

    response = manuelle(client, comptable, db, [frais], compte="44110000", taux_tva="10")

    assert response.status_code == 200, response.text
    ecrite = lire(client, comptable, db, None).json()["ecritures"][0]
    assert [(ligne["compte"], ligne["debit"]) for ligne in ecrite["lignes"]] == [
        ("44110000", "150.00"),
        ("34552142", "15.00"),
        ("55410003", None),
    ]
    audit = db.scalar(select(AuditLog).filter_by(action="comptabilisation_manuelle"))
    assert audit.nouvelle_valeur["compte_charge"] == "44110000"
    assert audit.nouvelle_valeur["compte_libre"] is True


# --- Frais déjà inclus dans une écriture Sage (13/10/2026) ---------------------------------------


def virement_et_frais(db, compte, jour=JOUR):
    virement = operation(db, compte, "-10000", jour, "VIREMENT EMIS FOURNISSEUR X")
    commission = operation(db, compte, "-50", jour, "COMMISSION")
    tva = operation(db, compte, "-5", jour, "TAXE SUR VALEUR AJOUTEE")
    return virement, commission, tva


def test_fees_inside_a_sage_entry_are_neither_proposed_nor_booked(client, comptable, db):
    """Le groupe « opération principale + frais » couvre ses frais (15/10/2026), et un frais seul
    face à une écriture Sage de frais du même montant à `fenetre_jours` près aussi (05/11/2026) ;
    face à une écriture qui n'est pas un frais, il se comptabilise dans SIMTIS."""
    compte = bp(db)
    _, commission, tva = virement_et_frais(db, compte)
    agios = operation(db, compte, "-30", JOUR, "AGIOS BANCAIRES")
    frais = operation(db, compte, "-40", JOUR, "FRAIS DE TENUE DE COMPTE")
    ecriture(db, compte, "10055", JOUR, "VIR FOURNISSEUR X")
    ecriture(db, compte, "30", date(2026, 4, 25), "AGIOS AVRIL")
    ecriture(db, compte, "40", JOUR, "VIR CLIENT Y")

    body = lire(client, comptable, db, None).json()
    automatique = valider(client, comptable, db, (compte, JOUR), famille="commissions")

    assert body["propositions"] == []
    inclus = {item["id"]: item["ecriture"]["libelle"] for item in body["frais_inclus"]}
    assert inclus == {
        commission.id: "VIR FOURNISSEUR X",
        tva.id: "VIR FOURNISSEUR X",
        agios.id: "AGIOS AVRIL",
    }
    assert [item["id"] for item in body["autres_frais"]] == [frais.id]
    assert automatique.status_code == 409
    assert manuelle(client, comptable, db, [agios]).status_code == 409
    assert manuelle(client, comptable, db, [frais]).status_code == 200


def test_a_rejected_pair_or_an_unrelated_entry_does_not_block_a_fee(client, comptable, db):
    from datetime import UTC, datetime

    from app.models import ReconciliationMatch, ReconciliationMatchItem, User

    compte = bp(db)
    autre = account(db, bank_code="AWB")
    agios = operation(db, compte, "-30", JOUR, "AGIOS BANCAIRES")
    rejetee = ecriture(db, compte, "30", JOUR, "AGIOS AVRIL")
    ecriture(db, autre, "30", JOUR, "AGIOS AWB")  # autre compte
    ecriture(db, compte, "30", date(2026, 5, 4), "AGIOS MAI")  # 11 jours : hors fenêtre
    db.add(
        ReconciliationMatch(
            company_id=compte.company_id,
            type="1-1",
            statut="Rejetée",
            decide_par_id=db.scalar(select(User.id).filter_by(email="comptable@example.com")),
            decide_le=datetime.now(UTC),
            items=[
                ReconciliationMatchItem(bank_transaction_id=agios.id, montant_affecte=30),
                ReconciliationMatchItem(accounting_entry_id=rejetee.id, montant_affecte=30),
            ],
        )
    )
    db.flush()

    body = lire(client, comptable, db, None).json()

    assert body["frais_inclus"] == []
    assert [item["id"] for item in body["autres_frais"]] == [agios.id]


# --- Écriture « FRAIS » : frais à TVA comprise (14/10/2026) ---------------------------------------


@pytest.mark.parametrize(
    ("libelle", "attendu"),
    [
        # Les commissions à TVA comprise vont dans la COM du jour, pas dans « FRAIS »
        ("COMMISSION VIR. RTGS EMIS VERS BMCE EN FAVEUR DE X", None),
        ("COMMISSION BANCAIRE", None),
        ("FRAIS RECUPERES PAR LA BANQUE", "frais_recuperes"),
        ("FRAIS RÉCUPÉRÉS PAR LA BANQUE", "frais_recuperes"),
        ("FRAIS DE TENUE DE COMPTE", None),
        ("AGIOS BANCAIRES", None),
        ("COMMISSION", None),
    ],
)
def test_fees_with_vat_inside_are_recognised(libelle, attendu):
    assert type_frais_tva(libelle) == attendu


@pytest.mark.parametrize(
    ("libelle", "attendu"),
    [
        ("COMMISSION VIR. RTGS EMIS VERS BMCE EN FAVEUR DE X", "commission_rtgs"),
        ("COMMISSION REGLEMENT PRELEVEMENT EN FAVEUR DE MAROC LEASING", "commission_prelevement"),
        ("COMMISSION BANCAIRE", "commission_bancaire"),
        ("COMMISSION TENUE DE COMPTE", "commission_tenue"),
        ("COMMISSION", "commission"),
        ("COMMISSION COTISATIONS CNSS", None),
        ("FRAIS RECUPERES PAR LA BANQUE", None),
    ],
)
def test_commissions_with_vat_inside_go_to_the_com_entry(libelle, attendu):
    assert type_commission(libelle) == attendu


@pytest.mark.parametrize(
    ("code", "montant", "parts"),
    [
        (
            "commission_rtgs",
            "165.00",
            [("commission_rtgs", "150.00"), ("commission_rtgs_tva", "15.00")],
        ),
        (
            "commission_prelevement",
            "11.00",
            [("commission_prelevement", "10.00"), ("commission_prelevement_tva", "1.00")],
        ),
        (
            "frais_recuperes",
            "355.00",
            [("frais_recuperes", "322.73"), ("frais_recuperes_tva", "32.27")],
        ),
        (
            "frais_recuperes",
            "77.50",
            [
                ("frais_recuperes", "25.00"),
                ("frais_recuperes_tva", "2.50"),
                ("frais_recuperes_timbre", "50.00"),
            ],
        ),
        ("commission", "20.00", [("commission", "20.00")]),
    ],
)
def test_vat_and_stamp_are_split_from_each_fee(code, montant, parts):
    resultat = ventilation(code, Decimal(montant))

    assert resultat == [(nom, Decimal(valeur)) for nom, valeur in parts]
    assert sum(valeur for _, valeur in resultat) == Decimal(montant)


def frais_tva_du_jour(db, compte, jour=JOUR):
    return [
        operation(db, compte, "-165", jour, "COMMISSION VIR. RTGS EMIS VERS BMCE EN FAVEUR DE X"),
        operation(db, compte, "-77.50", jour, "FRAIS RECUPERES PAR LA BANQUE"),
        operation(db, compte, "-11", jour, "COMMISSION REGLEMENT PRELEVEMENT EN FAVEUR DE X"),
        # Un remboursement reste à la main
        operation(db, compte, "73558.97", jour, "COMMISSION BANCAIRE"),
    ]


def test_commissions_go_to_com_and_frais_recuperes_to_frais_with_computed_vat(
    client, comptable, db
):
    compte = bp(db)
    rtgs, recuperes, prelevement, remboursement = frais_tva_du_jour(db, compte)
    libelle_rtgs = "COMMISSION VIR. RTGS EMIS VERS BMCE EN FAVEUR DE X"
    libelle_prelevement = "COMMISSION REGLEMENT PRELEVEMENT EN FAVEUR DE X"
    libelle_recuperes = "FRAIS RECUPERES PAR LA BANQUE"

    tous = lire(client, comptable, db, None).json()
    com, frais = (lire(client, comptable, db, nom).json() for nom in ("commissions", "frais"))

    # COMMISSION… → « COM » ; FRAIS… → « FRAIS » (14/10/2026) ; une écriture par frais, avec sa
    # TVA (et son timbre) comprise (13/11/2026)
    assert [(p["libelle"], p["total"]) for p in com["propositions"]] == [
        ("COM", "165.00"),
        ("COM", "11.00"),
    ]
    assert [
        [(ligne["type_libelle"], ligne["debit"], ligne["credit"]) for ligne in p["lignes"]]
        for p in com["propositions"]
    ] == [
        [
            ("Commission RTGS", "150.00", None),
            ("TVA commission RTGS", "15.00", None),
            ("Banque", None, "165.00"),
        ],
        [
            ("Commission prélèvement", "10.00", None),
            ("TVA commission prélèvement", "1.00", None),
            ("Banque", None, "11.00"),
        ],
    ]
    [ecriture_frais] = frais["propositions"]
    assert (ecriture_frais["libelle"], ecriture_frais["total"]) == ("FRAIS", "77.50")
    assert [
        (ligne["type_libelle"], ligne["compte"], ligne["debit"], ligne["credit"])
        for ligne in ecriture_frais["lignes"]
    ] == [
        ("Frais récupérés", "61473000", "25.00", None),
        ("TVA frais récupérés", "34552142", "2.50", None),
        ("Timbre frais récupérés", "61671000", "50.00", None),
        ("Banque", "55410003", None, "77.50"),
    ]
    assert [a["id"] for a in tous["autres_frais"]] == [remboursement.id]

    body = {
        "company_id": company(db).id,
        "jours": [
            {"famille": nom, "bank_account_id": compte.id, "date": str(JOUR)}
            for nom in ("commissions", "frais")
        ],
    }
    response = client.post("/api/frais/valider", json=body, headers=comptable)
    assert response.status_code == 200, response.text
    assert statuses(db, rtgs, recuperes, prelevement, remboursement) == [
        "Rapprochée",
        "Rapprochée",
        "Rapprochée",
        "Non rapprochée",
    ]
    assert "comptabilisation_frais" in actions(db)

    # Numérotés à l'export par date puis ordre de validation : RTGS, prélèvement, FRAIS ; toutes
    # les lignes au libellé du relevé (13/11/2026)
    rows = lignes_csv(exporter(client, comptable, db))
    assert [(r[1], r[3], r[5], r[6], r[7]) for r in rows] == [
        ("BP2604001", "61473000", libelle_rtgs, "150,00", "D"),
        ("BP2604001", "34552142", libelle_rtgs, "15,00", "D"),
        ("BP2604001", "55410003", libelle_rtgs, "165,00", "C"),
        ("BP2604002", "61473000", libelle_prelevement, "10,00", "D"),
        ("BP2604002", "34552142", libelle_prelevement, "1,00", "D"),
        ("BP2604002", "55410003", libelle_prelevement, "11,00", "C"),
        ("BP2604003", "61473000", libelle_recuperes, "25,00", "D"),
        ("BP2604003", "34552142", libelle_recuperes, "2,50", "D"),
        ("BP2604003", "61671000", libelle_recuperes, "50,00", "D"),
        ("BP2604003", "55410003", libelle_recuperes, "77,50", "C"),
    ]
    # Même libellé à l'écran
    assert {ligne["libelle"] for ligne in ecriture_frais["lignes"]} == {libelle_recuperes}


def test_a_day_with_a_sage_frais_entry_is_not_proposed(client, comptable, db):
    """L'écriture Sage « FRAIS » du total du jour (déjà rapprochée : pas « inclus ») couvre ses
    frais (13/11/2026 : un autre montant ne bloque plus le jour)."""
    compte = bp(db)
    frais_tva_du_jour(db, compte)
    ecriture(db, compte, "77.50", JOUR, "FRAIS", statut="Rapprochée")

    assert lire(client, comptable, db, "frais").json()["propositions"] == []


# --- N° de pièce BANQUE AAMMNNN (16/10/2026) -----------------------------------------------------


def test_a_piece_number_is_bank_year_month_and_three_digits():
    assert numero_piece("BP", date(2026, 10, 3), 123) == "BP2610123"
    assert numero_piece("AWB", date(2027, 1, 31), 1) == "AWB2701001"
    with pytest.raises(ConflictError, match="épuisé"):
        numero_piece("BP", date(2026, 10, 3), 1000)


def test_pieces_are_given_at_export_from_the_first_one_typed(client, comptable, db):
    """09/11/2026 : un fichier par banque et par mois, numéroté à partir du N° saisi, dans l'ordre
    des dates ; les autres mois et les autres banques ne sont pas touchés."""
    compte = bp(db)
    awb = account(db, bank_code="AWB")
    awb.journal_sage = "5141"
    awb.compte_comptable = "55410001"
    db.flush()
    autre_jour = JOUR + timedelta(days=1)
    mois_suivant = date(JOUR.year, JOUR.month % 12 + 1, 1)
    # Un timbre par jour : une écriture chacun
    for jour in (autre_jour, JOUR, mois_suivant):
        operation(db, compte, "-202", jour, REMISE)
        assert valider(client, comptable, db, (compte, jour)).status_code == 200
    operation(db, awb, "-202", JOUR, REMISE)
    valider(client, comptable, db, (awb, JOUR))

    avant = a_exporter(client, comptable, db)
    assert [(i["bank_code"], i["mois"], i["nb"]) for i in avant] == [
        ("AWB", "2026-04", 1),
        ("BP", "2026-04", 2),
        ("BP", f"{mois_suivant:%Y-%m}", 1),
    ]

    response = exporter(client, comptable, db, premiere=" bp2604017 ")

    assert response.status_code == 200, response.text
    assert "BP-2026-04" in response.headers["content-disposition"]
    assert [(r[0], r[1]) for r in lignes_csv(response)] == [
        # Le timbre au débit, la banque au crédit
        *[(f"{JOUR:%d/%m/%Y}", "BP2604017")] * 2,
        *[(f"{autre_jour:%d/%m/%Y}", "BP2604018")] * 2,
    ]
    pieces = dict(
        db.execute(
            select(AccountingEntry.date_ecriture, AccountingEntry.numero_piece).filter_by(
                origine="SIMTIS", bank_account_id=compte.id
            )
        ).all()
    )
    assert pieces == {JOUR: "BP2604017", autre_jour: "BP2604018", mois_suivant: None}
    assert [(i["bank_code"], i["mois"]) for i in a_exporter(client, comptable, db)] == [
        ("AWB", "2026-04"),
        ("BP", f"{mois_suivant:%Y-%m}"),
    ]
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "export_frais_sage"))
    assert (audit.nouvelle_valeur["premiere_piece"], audit.nouvelle_valeur["derniere_piece"]) == (
        "BP2604017",
        "BP2604018",
    )


def a_exporter(client, headers, db):
    response = client.get(
        "/api/frais/a-exporter", params={"company_id": company(db).id}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize(
    ("premiere", "message"),
    [
        ("AWB2604001", "BP2604 suivi de 3 chiffres"),
        ("BP2605001", "BP2604 suivi de 3 chiffres"),
        ("BP260401", "BP2604 suivi de 3 chiffres"),
        ("BP2604000", "BP2604 suivi de 3 chiffres"),
        ("BP2604999", "dépassent BP2604999"),
    ],
)
def test_the_first_piece_must_match_the_bank_and_the_month(
    client, comptable, db, premiere, message
):
    compte = bp(db)
    for jour in (JOUR, JOUR + timedelta(days=1)):
        timbres_du_jour(db, compte, jour)
        valider(client, comptable, db, (compte, jour))

    response = exporter(client, comptable, db, premiere=premiere)

    assert response.status_code == 409
    assert message in response.json()["detail"]
    exportee = select(AccountingEntry.id).where(AccountingEntry.exportee_le.is_not(None))
    assert db.scalar(exportee) is None


def test_the_export_list_needs_a_login(client, direction, db):
    params = {"company_id": company(db).id}
    assert client.get("/api/frais/a-exporter", params=params).status_code == 401
    assert a_exporter(client, direction, db) == []


# --- Propositions modifiées ou écartées (19/10/2026) ----------------------------------------------


def valider_modifie(client, headers, db, compte, **modif):
    body = {
        "company_id": company(db).id,
        "jours": [{"famille": "timbres", "bank_account_id": compte.id, "date": str(JOUR), **modif}],
    }
    return client.post("/api/frais/valider", json=body, headers=headers)


def test_a_proposal_is_validated_with_its_label_date_and_lines_changed(client, comptable, db):
    compte = bp(db)
    # Un jour d'une seule écriture : la modification sans opération s'y applique
    operation(db, compte, "-202", JOUR, REMISE)
    lignes = [
        {"compte": "61671", "libelle": "DT VERSEMENTS", "montant": "2.00", "sens": "Débit"},
        {"compte": "61473000", "libelle": "DT REMISE LCN", "montant": "200.00", "sens": "Débit"},
    ]

    response = valider_modifie(
        client,
        comptable,
        db,
        compte,
        libelle="dt avril",
        date_ecriture=str(JOUR + timedelta(days=2)),
        lignes=lignes,
    )

    assert response.status_code == 200, response.text
    entry = db.scalar(select(AccountingEntry).filter_by(origine="SIMTIS"))
    assert (entry.libelle, entry.date_ecriture, entry.montant) == (
        "DT AVRIL",
        JOUR + timedelta(days=2),
        Decimal("202.00"),
    )
    [ecrite] = lire(client, comptable, db).json()["ecritures"]
    assert ecrite["modifiee"] is True
    assert [(g["compte"], g["libelle"], g["debit"]) for g in ecrite["lignes"]] == [
        ("61671", "DT VERSEMENTS", "2.00"),
        ("61473000", "DT REMISE LCN", "200.00"),
        # La ligne banque, jamais saisie, au libellé du relevé (13/11/2026)
        ("55410003", REMISE, None),
    ]
    # La ligne banque est ajoutée aux lignes saisies (11/11/2026)
    rows = lignes_csv(exporter(client, comptable, db))
    assert [(r[0], r[3], r[5], r[6], r[7]) for r in rows] == [
        ("25/04/2026", "61671", "DT VERSEMENTS", "2,00", "D"),
        ("25/04/2026", "61473000", "DT REMISE LCN", "200,00", "D"),
        ("25/04/2026", "55410003", REMISE, "202,00", "C"),
    ]
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "comptabilisation_timbres"))
    assert audit.nouvelle_valeur["modifiee"] is True


def test_changed_lines_must_make_the_total_and_the_date_stay_in_bounds(client, comptable, db):
    compte = bp(db)
    operation(db, compte, "-202", JOUR, REMISE)
    faux = [{"compte": "61671", "libelle": "DT", "montant": "200.00", "sens": "Débit"}]

    total = valider_modifie(client, comptable, db, compte, lignes=faux)
    avant = valider_modifie(
        client, comptable, db, compte, date_ecriture=str(JOUR - timedelta(days=1))
    )

    assert total.status_code == 409
    assert "écart 2.00" in total.json()["detail"]
    assert avant.status_code == 409
    assert db.scalar(select(AccountingEntry).filter_by(origine="SIMTIS")) is None


def test_a_dismissed_day_goes_to_the_fees_booked_by_hand_until_proposed_again(
    client, comptable, direction, db
):
    compte = bp(db)
    timbres = timbres_du_jour(db, compte)
    jour = {"famille": "timbres", "bank_account_id": compte.id, "date": str(JOUR)}
    body = {"company_id": company(db).id, "jours": [jour], "motif": "Déjà payé autrement"}

    assert client.post("/api/frais/ecarter", json=body, headers=direction).status_code == 403
    response = client.post("/api/frais/ecarter", json=body, headers=comptable)

    assert response.status_code == 200, response.text
    tableau = lire(client, comptable, db, None).json()
    assert tableau["propositions"] == []
    assert {a["id"] for a in tableau["autres_frais"]} == {tx.id for tx in timbres}
    [ecarte] = tableau["ecartes"]
    assert (ecarte["famille"], ecarte["date"], ecarte["motif"]) == (
        "timbres",
        str(JOUR),
        "Déjà payé autrement",
    )
    # Deux fois : la journée n'est plus proposée
    assert client.post("/api/frais/ecarter", json=body, headers=comptable).status_code == 409
    assert manuelle(client, comptable, db, timbres, libelle="DT").status_code == 200

    # Reproposer : plus rien à proposer (les timbres sont passés à la main), la ligne disparaît
    retour = client.post(
        "/api/frais/reproposer",
        json={"company_id": company(db).id, "jours": [jour]},
        headers=comptable,
    )
    assert retour.status_code == 200
    assert lire(client, comptable, db, None).json()["ecartes"] == []
    assert "ecartement_frais" in actions(db) and "reproposition_frais" in actions(db)


def test_a_dismissed_day_comes_back_when_proposed_again(client, comptable, db):
    compte = bp(db)
    timbres_du_jour(db, compte)
    jour = {"famille": "timbres", "bank_account_id": compte.id, "date": str(JOUR)}
    client.post(
        "/api/frais/ecarter",
        json={"company_id": company(db).id, "jours": [jour]},
        headers=comptable,
    )

    client.post(
        "/api/frais/reproposer",
        json={"company_id": company(db).id, "jours": [jour]},
        headers=comptable,
    )

    totaux = [p["total"] for p in lire(client, comptable, db).json()["propositions"]]
    assert totaux == ["200.00", "1.00", "1.00"]


def test_a_modification_names_its_fee_on_a_day_of_several_fees(client, comptable, db):
    """13/11/2026 : un jour de plusieurs écritures, une modification sans opération est refusée ;
    avec l'opération, elle ne touche que son écriture."""
    compte = bp(db)
    remise, _, _ = timbres_du_jour(db, compte)

    sans = valider_modifie(client, comptable, db, compte, libelle="DT")
    avec = valider_modifie(
        client, comptable, db, compte, transaction_id=remise.id, libelle="dt remise"
    )

    assert sans.status_code == 409
    assert "modifiez-les un par un" in sans.json()["detail"]
    assert avec.status_code == 200, avec.text
    entry = db.scalar(select(AccountingEntry).filter_by(origine="SIMTIS"))
    assert (entry.libelle, entry.montant) == ("DT REMISE", Decimal("200.00"))
    assert len(lire(client, comptable, db).json()["propositions"]) == 2


def test_one_fee_is_dismissed_alone_and_proposed_again(client, comptable, db):
    """13/11/2026 : « Écarter » porte sur l'opération ; les autres frais du jour restent proposés."""
    compte = bp(db)
    remise, versement, _ = timbres_du_jour(db, compte)
    choix = {
        "famille": "timbres",
        "bank_account_id": compte.id,
        "date": str(JOUR),
        "transaction_id": remise.id,
    }
    body = {"company_id": company(db).id, "jours": [choix], "motif": "Contesté"}

    response = client.post("/api/frais/ecarter", json=body, headers=comptable)

    assert response.status_code == 200, response.text
    tableau = lire(client, comptable, db, None).json()
    assert [p["total"] for p in tableau["propositions"]] == ["1.00", "1.00"]
    assert [a["id"] for a in tableau["autres_frais"]] == [remise.id]
    [ecarte] = tableau["ecartes"]
    assert (
        ecarte["transaction_id"],
        ecarte["libelle_operation"],
        ecarte["montant"],
        ecarte["motif"],
    ) == (remise.id, REMISE, "-200.00", "Contesté")
    # Le même frais deux fois : il n'est plus proposé
    assert client.post("/api/frais/ecarter", json=body, headers=comptable).status_code == 409
    # Les autres frais du jour s'écartent encore un par un
    autre = {**choix, "transaction_id": versement.id}
    assert (
        client.post(
            "/api/frais/ecarter",
            json={"company_id": company(db).id, "jours": [autre]},
            headers=comptable,
        ).status_code
        == 200
    )

    retour = client.post(
        "/api/frais/reproposer",
        json={"company_id": company(db).id, "jours": [choix]},
        headers=comptable,
    )

    assert retour.status_code == 200, retour.text
    assert [p["total"] for p in lire(client, comptable, db).json()["propositions"]] == [
        "200.00",
        "1.00",
    ]
    audit = db.scalar(
        select(AuditLog).where(AuditLog.action == "ecartement_frais").order_by(AuditLog.id)
    )
    assert audit.nouvelle_valeur["operation"] == remise.id


# --- Frais de plus de 200 DH : à la main et à justifier (19/10/2026) -----------------------------


def test_a_fee_above_200_leaves_the_automatic_proposal_but_a_stamp_does_not(client, comptable, db):
    compte = bp(db)
    petite = operation(db, compte, "-150", JOUR, "COMMISSION")
    # À TVA comprise : toujours au seuil de 200 DH (11/11/2026)
    grande = operation(db, compte, "-250", JOUR, "COMMISSION BANCAIRE")
    timbre = operation(db, compte, "-300", JOUR, REMISE)

    tableau = lire(client, comptable, db, None).json()

    totaux = {p["famille"]: p["total"] for p in tableau["propositions"]}
    assert totaux == {"commissions": "150.00", "timbres": "300.00"}
    assert [a["id"] for a in tableau["autres_frais"]] == [grande.id]
    assert valider(client, comptable, db, (compte, JOUR), famille="commissions").status_code == 200
    assert statuses(db, petite, grande, timbre) == [
        "Rapprochée",
        "Non rapprochée",
        "Non rapprochée",
    ]
    # Elle se comptabilise à la main
    assert manuelle(client, comptable, db, [grande], libelle="COM").status_code == 200


def test_fees_above_200_are_exported_for_the_bank(client, comptable, direction, db):
    compte = bp(db)
    operation(db, compte, "-150", JOUR, "COMMISSION")
    grande = operation(db, compte, "-250", JOUR, "COMMISSION BANCAIRE", reference="R1")
    operation(db, compte, "-300", JOUR, REMISE)
    # Commission et TVA sur deux lignes : automatiques, pas à justifier (11/11/2026)
    operation(db, compte, "-300", JOUR, "COMMISSION")
    operation(db, compte, "-30", JOUR, TVA)
    operation(db, compte, "-400", JOUR, "COMMISSION EFFET N 12 REMIS PAR X")
    agios = operation(db, compte, "-604.71", date(2026, 4, 24), "AGIOS BANCAIRES")
    manuelle(client, comptable, db, [agios], libelle="AGIOS")
    params = {"company_id": str(company(db).id), "from": "2026-04-01", "to": "2026-04-30"}

    response = client.get("/api/frais/justificatif", params=params, headers=direction)

    assert response.status_code == 200, response.text
    rows = list(load_workbook(io.BytesIO(response.content)).active.iter_rows(values_only=True))
    assert rows[0][:8] == (
        "Banque",
        "Compte",
        "Date d'opération",
        "Date de valeur",
        "Libellé",
        "Référence",
        "Montant",
        "Statut",
    )
    assert [(r[0], r[4], r[5], r[6], r[7]) for r in rows[1:3]] == [
        ("BP", "COMMISSION BANCAIRE", "R1", 250, "À comptabiliser"),
        ("BP", "AGIOS BANCAIRES", None, 604.71, "Comptabilisé"),
    ]
    assert rows[2][8] is None  # pas encore exportée : pas de N° pièce (09/11/2026)
    assert rows[3][0] == "Total BP" and rows[3][6] == 854.71
    assert rows[4][0] == "Total général"
    assert grande.id and "export_frais_banque" in actions(db)


# --- TVA d'une commission seulement dans la COM (09/11/2026) --------------------------------------

TVA = "TAXE SUR VALEUR AJOUTEE"
INTERET_ESCOMPTE = "INTERET REMISE LCN A L'ESCOMPTE"


def test_a_vat_goes_with_a_commission_of_ten_times_its_amount():
    """Relevé BP du 22/04/2026 : la TVA d'un intérêt d'escompte n'a pas de commission, celle d'une
    commission de plus de 200 DH entre avec elle (11/11/2026) ; une commission ne prend qu'une TVA."""
    autre_jour = date(2026, 4, 24)
    operations = [
        _tx(1, 1, JOUR, "-45", "COMMISSION"),
        _tx(2, 1, JOUR, "-4524.56", INTERET_ESCOMPTE),
        _tx(3, 1, JOUR, "-600", "COMMISSION"),
        _tx(4, 1, JOUR, "-4.50", TVA),  # 10 % de 45
        _tx(5, 1, JOUR, "-452.46", TVA),  # 10 % de l'intérêt
        _tx(6, 1, JOUR, "-60", TVA),  # 10 % de la commission de 600
        _tx(7, 1, JOUR, "-4.50", TVA),  # la commission de 45 a déjà sa TVA
        _tx(8, 2, JOUR, "-4.50", TVA),  # autre compte
        _tx(9, 1, date(2026, 4, 27), "-4.50", TVA),  # jour sans commission
        _tx(10, 1, autre_jour, "-44.96", "COMMISSION"),
        _tx(11, 1, autre_jour, "-4.50", TVA),  # 4,496 arrondi à 4,50
        _tx(12, 1, autre_jour, "-4.51", TVA),  # au centime près
    ]

    assert frais_service.tva_a_la_main(operations) == {5, 7, 8, 9, 12}


def test_a_vat_without_its_commission_is_booked_by_hand(client, comptable, db):
    compte = bp(db)
    commission = operation(db, compte, "-45", JOUR, "COMMISSION")
    operation(db, compte, "-196.82", JOUR, INTERET_ESCOMPTE)
    tva_commission = operation(db, compte, "-4.50", JOUR, TVA)
    # 10 % de l'intérêt, sous 200 DH : avant le 09/11/2026 elle entrait dans la COM
    tva_interet = operation(db, compte, "-19.68", JOUR, TVA)

    tableau = lire(client, comptable, db, None).json()

    # Une écriture par opération (13/11/2026) : la commission, puis sa TVA
    assert [(p["famille"], p["total"]) for p in tableau["propositions"]] == [
        ("commissions", "45.00"),
        ("commissions", "4.50"),
    ]
    assert tva_interet.id in {a["id"] for a in tableau["autres_frais"]}
    assert tva_commission.id not in {a["id"] for a in tableau["autres_frais"]}
    # La TVA de la commission ne se passe pas à la main, celle de l'intérêt oui
    assert manuelle(client, comptable, db, [tva_commission], libelle="TVA").status_code == 409
    assert valider(client, comptable, db, (compte, JOUR), famille="commissions").status_code == 200
    assert statuses(db, commission, tva_commission, tva_interet) == [
        "Rapprochée",
        "Rapprochée",
        "Non rapprochée",
    ]
    assert manuelle(client, comptable, db, [tva_interet], libelle="TVA").status_code == 200


def test_a_commission_above_200_goes_automatically_with_its_vat(client, comptable, db):
    """Décision du 11/11/2026 : commission et TVA sur deux lignes passent dans la COM même
    au-dessus de 200 DH (à la main avant)."""
    compte = bp(db)
    petite = operation(db, compte, "-40", JOUR, "COMMISSION")
    grande = operation(db, compte, "-600", JOUR, "COMMISSION")
    tva_petite = operation(db, compte, "-4", JOUR, TVA)
    tva_grande = operation(db, compte, "-60", JOUR, TVA)

    tableau = lire(client, comptable, db, None).json()

    # Une écriture par opération, dans l'ordre du relevé (13/11/2026)
    assert [(p["libelle"], p["total"]) for p in tableau["propositions"]] == [
        ("COM", "40.00"),
        ("COM", "600.00"),
        ("COM", "4.00"),
        ("COM", "60.00"),
    ]
    grande_com = tableau["propositions"][1]
    assert [
        (ligne["compte"], ligne["debit"], ligne["credit"]) for ligne in grande_com["lignes"]
    ] == [
        ("61473000", "600.00", None),
        ("55410003", None, "600.00"),
    ]
    assert tableau["autres_frais"] == []
    assert valider(client, comptable, db, (compte, JOUR), famille="commissions").status_code == 200
    assert statuses(db, petite, grande, tva_petite, tva_grande) == ["Rapprochée"] * 4


def test_other_banks_commission_pairs_above_200_are_automatic_too(client, comptable, db):
    compte = bp(db)
    transfert = operation(db, compte, "-500", JOUR, "TRANSFERT EMIS, COMMISSION DE TRANSFERT TRF 1")
    tva = operation(db, compte, "-50", JOUR, "TVA 10% SUR COMMISSION TRF 1")
    effet = operation(db, compte, "-250", JOUR, "COMMISSION EFFET N 12 REMIS PAR X")

    tableau = lire(client, comptable, db, None).json()

    assert [p["total"] for p in tableau["propositions"]] == ["500.00", "50.00", "250.00"]
    assert tableau["autres_frais"] == []
    assert transfert.id and tva.id and effet.id


def test_a_day_with_a_sage_com_entry_keeps_its_vat_out_of_the_manual_list(client, comptable, db):
    """Sage a déjà la COM du jour (son total, 13/11/2026) : toutes ses TVA y sont, aucune ne se
    passe à la main."""
    compte = bp(db)
    operation(db, compte, "-45", JOUR, "COMMISSION")
    # TVA de l'intérêt de 196,82 (sous 200 DH, sinon elle passerait à la main de toute façon)
    tva_interet = operation(db, compte, "-19.68", JOUR, TVA)
    ecriture(db, compte, "64.68", JOUR, "COM")

    tableau = lire(client, comptable, db, None).json()

    assert tableau["propositions"] == []
    assert tva_interet.id not in {a["id"] for a in tableau["autres_frais"]}


# --- Frais des autres banques, comme BP (09/11/2026) ----------------------------------------------


@pytest.mark.parametrize(
    ("libelle", "timbre", "commission", "frais"),
    [
        ("FRAIS DE TIMBRE/DOMICILIATION TITRE IMPORTATION REF : 7801926005299", True, None, None),
        ("FRAIS DE TIMBRE DOMICILIATION TITRES D'IMPORTATIONS", True, None, None),
        ("FRAIS TIMBRE DU MOIS 0926", True, None, None),
        ("DROIT DE TIMBRE SUR OPERATION", True, None, None),
        ("TRANSFERT EMIS, COMMISSION DE TRANSFERT TRF26J148345", False, "commission", None),
        ("TVA 10% SUR COMMISSION TRF26J148345", False, "tva", None),
        ("COMMISSION SUR VIREMENT SRBM POUR COMPTE AWB", False, "commission", None),
        ("TVA COMMISSION SUR VIREMENT SRBM POUR COMPTE AWB", False, "tva", None),
        ("COMMISSION REJET PAIEMENT LCN NUM 3 A L'ESCOMPTE", False, "commission_lcn", None),
        ("COM FRAIS REGLEMENT 1 LCN", False, "commission_lcn", None),
        ("COM FRAIS / 3 LCN PAYEES", False, "commission_lcn", None),
        ("COM FRAIS / 1 LCN IMPAYEES", False, "commission_lcn", None),
        ("COMMISSION DOMICILIATION TITRES D'IMPORTATIONS", False, "commission_domiciliation", None),
        ("COMMISSION DE TENUE DE COMPTE", False, "commission_tenue", None),
        ("FRAIS SWIFT CREDOC IMPORT EN FAVEUR DE X", False, None, "frais_swift"),
        ("FRAIS ENCAISSEMENT DE CHEQUES", False, None, "frais_cheques"),
        # CIH (11/11/2026), TVA comprise, sans seuil
        ("FRAIS CAUTION NUMERO 2600457", False, None, "frais_caution"),
        ("FRAIS CAUTION NUMÉRO : 26/00457", False, None, "frais_caution"),
        ("FRAIS PDL CREDOC IMPORT EN FAVEUR DE SOCIETE X", False, None, "frais_pdl_credoc"),
        # AWB (12/11/2026), TVA comprise, sans seuil (à la main avant)
        ("FRAIS RELEVE CAUTION", False, None, "frais_releve_caution"),
        ("COM.ADOBE", False, "commission_carte", None),
        ("COMM VIR SRBM: AWBVCA0510261805", False, "commission_virement", None),
        ("TIMBRE/REM LCN REF 1897734", True, None, None),
        # Restent à la main
        ("COMMISSION CAUTION", False, None, None),
        ("FRAIS ET AGIOS TRIMESTRIELS T3 2026", False, None, None),
        ("AGIOS ESCOMPTE LCN N 2600114", False, None, None),
        ("TVA 10% SUR COMMISSION REF ILC26A0001", False, None, None),
        ("PRELEVEMENT DE LA TVA SUR L'ENSEMBLE DES FRAIS & COMMISSIONS", False, None, None),
        ("CREDOC IMPORT COMMISSION OUVERTURE ILC26A0001", False, None, None),
        ("FRAIS DE TENUE DE COMPTE", False, None, None),
    ],
)
def test_fees_of_the_other_banks_are_recognised(libelle, timbre, commission, frais):
    assert (est_timbre(libelle), type_commission(libelle), type_frais_tva(libelle)) == (
        timbre,
        commission,
        frais,
    )


def details(proposition):
    return [(d["type"], d["nb_operations"], d["total"]) for d in proposition["details"]]


def details_de(tableau, libelle):
    """Détails des écritures d'un libellé additionnés par type (une écriture par frais,
    13/11/2026) : {type: (nombre, total)}."""
    cumul: dict[str, tuple[int, Decimal]] = {}
    for proposition in tableau["propositions"]:
        if proposition["libelle"] != libelle:
            continue
        for d in proposition["details"]:
            nb, total = cumul.get(d["type"], (0, Decimal(0)))
            cumul[d["type"]] = (nb + d["nb_operations"], total + Decimal(d["total"]))
    return {code: (nb, f"{total:.2f}") for code, (nb, total) in cumul.items()}


def total_de(tableau, libelle):
    return str(sum(Decimal(p["total"]) for p in tableau["propositions"] if p["libelle"] == libelle))


def test_a_bmce_day_is_booked_like_bp(client, comptable, db):
    """Commission et TVA sur deux lignes, associées par les 10 % ; timbre de domiciliation ; une
    commission de plus de 200 DH entre dans la COM avec sa TVA (11/11/2026, à la main avant)."""
    compte = account(db, bank_code="BMCE")
    operation(db, compte, "-50", JOUR, "TRANSFERT EMIS, COMMISSION DE TRANSFERT TRF26J148345")
    operation(db, compte, "-5", JOUR, "TVA 10% SUR COMMISSION TRF26J148345")
    operation(db, compte, "-150", JOUR, "COMMISSION SUR VIREMENT SRBM POUR COMPTE AWB")
    operation(db, compte, "-15", JOUR, "TVA COMMISSION SUR VIREMENT SRBM POUR COMPTE AWB")
    operation(db, compte, "-50", JOUR, "FRAIS DE TIMBRE/DOMICILIATION TITRE IMPORTATION REF : 78")
    grande = operation(db, compte, "-423.20", JOUR, "TRANSFERT EMIS, COMMISSION DE TRANSFERT TRF9")
    tva_grande = operation(db, compte, "-42.32", JOUR, "TVA 10% SUR COMMISSION TRF9")

    tableau = lire(client, comptable, db, None).json()

    # Une écriture par opération (13/11/2026) : le timbre, puis chaque commission et chaque TVA
    assert [(p["libelle"], p["total"], details(p)) for p in tableau["propositions"]] == [
        ("DT D'ENREGISTREMENT", "50.00", [("timbre", 1, "50.00")]),
        ("COM", "50.00", [("commission", 1, "50.00")]),
        ("COM", "5.00", [("tva", 1, "5.00")]),
        ("COM", "150.00", [("commission", 1, "150.00")]),
        ("COM", "15.00", [("tva", 1, "15.00")]),
        ("COM", "423.20", [("commission", 1, "423.20")]),
        ("COM", "42.32", [("tva", 1, "42.32")]),
    ]
    assert tableau["autres_frais"] == []
    assert grande.id and tva_grande.id


def test_awb_fees_with_vat_inside_are_split_and_its_escompte_stays_by_hand(client, comptable, db):
    compte = account(db, bank_code="AWB")
    operation(db, compte, "-22", JOUR, "COMMISSION REJET PAIEMENT LCN NUM 3100482 A L'ESCOMPTE")
    operation(db, compte, "-39.60", JOUR, "FRAIS SWIFT CREDOC IMPORT EN FAVEUR DE X")
    operation(db, compte, "-28", JOUR, "FRAIS TIMBRE DU MOIS 0926")
    agios = operation(db, compte, "-73.15", JOUR, "AGIOS ESCOMPTE LCN N 2600114")

    tableau = lire(client, comptable, db, None).json()

    par_famille = {p["famille"]: p for p in tableau["propositions"]}
    assert details(par_famille["commissions"]) == [
        ("commission_lcn", 1, "20.00"),
        ("commission_lcn_tva", 1, "2.00"),
    ]
    assert details(par_famille["frais"]) == [
        ("frais_swift", 1, "36.00"),
        ("frais_swift_tva", 1, "3.60"),
    ]
    assert [(g["compte"], g["debit"]) for g in par_famille["frais"]["lignes"]][:2] == [
        ("61473000", "36.00"),
        ("34552142", "3.60"),
    ]
    assert par_famille["timbres"]["total"] == "28.00"
    assert [a["id"] for a in tableau["autres_frais"]] == [agios.id]


def test_cih_caution_and_pdl_credoc_fees_are_automatic_whatever_the_amount(
    client, comptable, direction, db
):
    """11/11/2026 : FRAIS CAUTION NUMERO et FRAIS PDL CREDOC IMPORT EN FAVEUR passent dans
    l'écriture « FRAIS », TVA de 10 % comprise, même au-dessus de 200 DH, et ne vont pas dans le
    fichier des frais à justifier."""
    compte = account(db, bank_code="CIH")
    operation(db, compte, "-110", JOUR, "FRAIS CAUTION NUMERO 2600457")
    operation(db, compte, "-660", JOUR, "FRAIS PDL CREDOC IMPORT EN FAVEUR DE SOCIETE X")
    releve = operation(db, compte, "-22", JOUR, "FRAIS DE DOSSIER CAUTION")

    tableau = lire(client, comptable, db, None).json()

    # Une écriture par frais, sa TVA comprise (13/11/2026)
    assert [
        (p["famille"], p["libelle"], p["total"], details(p)) for p in tableau["propositions"]
    ] == [
        (
            "frais",
            "FRAIS",
            "110.00",
            [("frais_caution", 1, "100.00"), ("frais_caution_tva", 1, "10.00")],
        ),
        (
            "frais",
            "FRAIS",
            "660.00",
            [("frais_pdl_credoc", 1, "600.00"), ("frais_pdl_credoc_tva", 1, "60.00")],
        ),
    ]
    assert [
        (g["compte"], g["debit"], g["credit"]) for g in tableau["propositions"][1]["lignes"]
    ] == [
        ("61473000", "600.00", None),
        ("34552142", "60.00", None),
        (compte.compte_comptable, None, "660.00"),
    ]
    assert [a["id"] for a in tableau["autres_frais"]] == [releve.id]

    params = {"company_id": str(company(db).id), "from": "2026-04-01", "to": "2026-04-30"}
    response = client.get("/api/frais/justificatif", params=params, headers=direction)
    assert response.status_code == 409
    assert "Aucun frais de plus de 200 DH" in response.json()["detail"]


@pytest.mark.parametrize(
    ("banque", "attendu"),
    [("CIH", "agios_escompte"), ("AWB", None), ("BP", None), (None, None)],
)
def test_escompte_agios_are_a_cih_fee_with_vat_only(banque, attendu):
    """12/11/2026 : seule règle qui lit la banque ; sans seuil chez CIH seulement."""
    assert type_frais_tva("AGIOS ESCOMPTE LCN N° 2600114", banque) == attendu
    assert frais_service.sans_seuil("AGIOS ESCOMPTE LCN N 2600114", banque) is (attendu is not None)


def cih(db):
    compte = account(db, bank_code="CIH")
    compte.compte_comptable, compte.journal_sage = "55410005", "5545"
    db.flush()
    return compte


def test_cih_escompte_agios_are_automatic_with_vat_on_the_cih_agios_account(
    client, comptable, direction, db
):
    """12/11/2026 : chez CIH, « AGIOS ESCOMPTE LCN N … » entre dans l'écriture « FRAIS », hors taxe
    sur 63116300 (AGIOS CIH) et TVA de 10 % comprise sur 34552142, quel que soit le montant ; un
    remboursement reste à la main ; chez AWB, le même libellé reste à la main."""
    compte = cih(db)
    petit = operation(db, compte, "-4.18", JOUR, "AGIOS ESCOMPTE LCN N 2600114")
    grand = operation(db, compte, "-21945", JOUR, "AGIOS ESCOMPTE LCN N° 2600115")
    remboursement = operation(db, compte, "50", JOUR, "AGIOS ESCOMPTE LCN N 2600116")
    chez_awb = operation(db, account(db, bank_code="AWB"), "-73.15", JOUR, petit.libelle)

    tableau = lire(client, comptable, db, None).json()

    # Une écriture par agio, sa TVA comprise (13/11/2026)
    assert [(p["famille"], p["libelle"], p["total"]) for p in tableau["propositions"]] == [
        ("frais", "FRAIS", "4.18"),
        ("frais", "FRAIS", "21945.00"),
    ]
    assert [
        [(g["compte"], g["debit"], g["credit"]) for g in p["lignes"]]
        for p in tableau["propositions"]
    ] == [
        [("63116300", "3.80", None), ("34552142", "0.38", None), ("55410005", None, "4.18")],
        [
            ("63116300", "19950.00", None),
            ("34552142", "1995.00", None),
            ("55410005", None, "21945.00"),
        ],
    ]
    assert {a["id"] for a in tableau["autres_frais"]} == {remboursement.id, chez_awb.id}

    # Sans seuil : pas dans le fichier des frais à justifier auprès de la banque
    params = {"company_id": str(company(db).id), "from": "2026-04-01", "to": "2026-04-30"}
    justificatif = client.get("/api/frais/justificatif", params=params, headers=direction)
    assert justificatif.status_code == 409
    assert "Aucun frais de plus de 200 DH" in justificatif.json()["detail"]

    assert valider(client, comptable, db, (compte, JOUR), famille="frais").status_code == 200
    response = exporter(client, comptable, db, banque="CIH")
    assert response.status_code == 200, response.text
    vides = ("",) * 7
    # Une pièce par agio, toutes ses lignes au libellé du relevé (13/11/2026)
    petit_l, grand_l = petit.libelle, grand.libelle
    assert lignes_csv(response) == [
        ("23/04/2026", "CIH2604001", "5545", "63116300", "", petit_l, "3,80", "D") + vides,
        ("23/04/2026", "CIH2604001", "5545", "34552142", "", petit_l, "0,38", "D") + vides,
        ("23/04/2026", "CIH2604001", "5545", "55410005", "", petit_l, "4,18", "C") + vides,
        ("23/04/2026", "CIH2604002", "5545", "63116300", "", grand_l, "19950,00", "D") + vides,
        ("23/04/2026", "CIH2604002", "5545", "34552142", "", grand_l, "1995,00", "D") + vides,
        ("23/04/2026", "CIH2604002", "5545", "55410005", "", grand_l, "21945,00", "C") + vides,
    ]


def test_cih_escompte_agios_are_not_proposed_on_a_day_already_in_sage(client, comptable, db):
    compte = cih(db)
    agios = operation(db, compte, "-4.18", JOUR, "AGIOS ESCOMPTE LCN N 2600114")
    # L'écriture « FRAIS » de Sage du même montant (13/11/2026), déjà rapprochée : pas « inclus »
    ecriture(db, compte, "4.18", JOUR, "FRAIS", statut="Rapprochée")

    tableau = lire(client, comptable, db, None).json()

    assert tableau["propositions"] == []
    assert agios.id not in {a["id"] for a in tableau["autres_frais"]}


def test_awb_fees_are_automatic_with_vat_except_quarterly_agios_and_bond_commission(
    client, comptable, db
):
    """12/11/2026 : commissions (virements, EBICS, carte) dans « COM », frais (Attijari Net,
    DocNet, certification, opération, relevé caution) dans « FRAIS », TVA 10 % comprise et sans
    seuil ; timbre LCN dans « DT D'ENREGISTREMENT » ; « COM & FRAIS » proposé ; agios trimestriels
    et commission caution restent à la main."""
    compte = account(db, bank_code="AWB")
    for montant, libelle in (
        ("-17.60", "COMM VIR EMIS 67783838"),
        ("-165", "COMM VIR SRBM: AWBVCA0510261805"),
        ("-660", "COM ABONNEMENT EBICS"),
        ("-11", "COM.ADOBE"),
        ("-82.50", "COM & FRAIS / 3 LCN PAYEES"),
        ("-71.50", "FRAIS ATTIJARI NET ENTREPRISE"),
        ("-214.50", "FRAIS MODULE DOCNET 5 ANS"),
        ("-44", "FRAIS POUR CERTIFICATION CHEQUES"),
        ("-33", "FRAIS OPERATION N 132593923"),
        ("-22", "FRAIS RELEVE CAUTION"),
        ("-40", "TIMBRE/REM LCN REF 1897734"),
    ):
        operation(db, compte, montant, JOUR, libelle)
    agios = operation(db, compte, "-47917.73", JOUR, "FRAIS ET AGIOS TRIMESTRIELS T3 2026")
    caution = operation(db, compte, "-2187.40", JOUR, "COMMISSION CAUTION")

    tableau = lire(client, comptable, db, None).json()

    # Une écriture par frais (13/11/2026) : 11 écritures, additionnées ici par type
    assert len(tableau["propositions"]) == 11
    assert {p["libelle"] for p in tableau["propositions"]} == {
        "DT D'ENREGISTREMENT",
        "COM",
        "FRAIS",
    }
    assert total_de(tableau, "DT D'ENREGISTREMENT") == "40.00"
    assert details_de(tableau, "COM") == {
        "commission_lcn": (1, "75.00"),
        "commission_lcn_tva": (1, "7.50"),
        "commission_virement": (2, "166.00"),
        "commission_virement_tva": (2, "16.60"),
        "commission_ebics": (1, "600.00"),
        "commission_ebics_tva": (1, "60.00"),
        "commission_carte": (1, "10.00"),
        "commission_carte_tva": (1, "1.00"),
    }
    assert total_de(tableau, "COM") == "936.10"
    assert details_de(tableau, "FRAIS") == {
        "frais_attijari_net": (1, "65.00"),
        "frais_attijari_net_tva": (1, "6.50"),
        "frais_docnet": (1, "195.00"),
        "frais_docnet_tva": (1, "19.50"),
        "frais_certification": (1, "40.00"),
        "frais_certification_tva": (1, "4.00"),
        "frais_operation": (1, "30.00"),
        "frais_operation_tva": (1, "3.00"),
        "frais_releve_caution": (1, "20.00"),
        "frais_releve_caution_tva": (1, "2.00"),
    }
    comptes = {g["compte"] for p in tableau["propositions"] for g in p["lignes"] if g["debit"]}
    assert comptes == {"61671000", "61473000", "34552142"}
    assert {a["id"] for a in tableau["autres_frais"]} == {agios.id, caution.id}


def awb(db):
    compte = account(db, bank_code="AWB")
    compte.compte_comptable, compte.journal_sage = "55410002", "5542,5242"
    db.flush()
    return compte


def test_every_line_of_an_entry_carries_the_statement_label(client, comptable, db):
    """13/11/2026 (remplace « la banque en détail, les charges regroupées » du 12/11/2026) : une
    écriture par opération ; toutes ses lignes, débit comme crédit, portent le libellé de
    l'opération du relevé (50 caractères au plus), à l'écran, une fois validée et dans le fichier
    pour Sage."""
    compte = awb(db)
    long = "COMM VIR SRBM: AWBVCA0510261805 POUR LE COMPTE DE SOCIETE X SARL"
    operation(db, compte, "-660", JOUR, "COM ABONNEMENT EBICS")
    operation(db, compte, "-165", JOUR, long)
    operation(db, compte, "-11", JOUR, "COM.ADOBE")
    libelles = ["COM ABONNEMENT EBICS", long[:50], "COM.ADOBE"]

    propositions = lire(client, comptable, db, None).json()["propositions"]

    assert [
        [(g["compte"], g["libelle"], g["debit"], g["credit"]) for g in p["lignes"]]
        for p in propositions
    ] == [
        [
            ("61473000", libelle, ht, None),
            ("34552142", libelle, tva, None),
            (compte.compte_comptable, libelle, None, total),
        ]
        for libelle, ht, tva, total in (
            (libelles[0], "600.00", "60.00", "660.00"),
            (libelles[1], "150.00", "15.00", "165.00"),
            (libelles[2], "10.00", "1.00", "11.00"),
        )
    ]

    response = valider(client, comptable, db, (compte, JOUR), famille="commissions")
    assert response.status_code == 200, response.text
    validees = lire(client, comptable, db, None).json()["ecritures"]
    assert sorted({g["libelle"] for e in validees for g in e["lignes"]}) == sorted(libelles)
    rows = lignes_csv(exporter(client, comptable, db, banque="AWB"))
    assert [row[5] for row in rows] == [libelle for libelle in libelles for _ in range(3)]


def test_a_modified_entry_keeps_one_bank_line_with_the_total(client, comptable, db):
    """Une écriture modifiée avant validation garde une seule ligne banque, le total, et ses
    libellés saisis."""
    compte = awb(db)
    operation(db, compte, "-660", JOUR, "COM ABONNEMENT EBICS")
    lignes = [
        {"compte": "61473000", "libelle": "COM", "montant": "660.00", "sens": "Débit"},
    ]
    body = {
        "company_id": company(db).id,
        "jours": [
            {
                "famille": "commissions",
                "bank_account_id": compte.id,
                "date": str(JOUR),
                "lignes": lignes,
            }
        ],
    }

    response = client.post("/api/frais/valider", json=body, headers=comptable)

    assert response.status_code == 200, response.text
    (validee,) = lire(client, comptable, db, None).json()["ecritures"]
    assert [(g["compte"], g["libelle"], g["credit"]) for g in validee["lignes"]] == [
        ("61473000", "COM", None),
        # La ligne banque, jamais saisie, au libellé du relevé (13/11/2026)
        (compte.compte_comptable, "COM ABONNEMENT EBICS", "660.00"),
    ]


def test_the_fees_journal_is_the_account_journal_starting_with_55(client, comptable, db):
    """10/11/2026 : « 1456,5541 » → les écritures de frais passent dans le journal 5541."""
    compte = account(db, bank_code="BMCE")
    compte.journal_sage = "1456,5541"
    compte.compte_comptable = "55410002"
    db.flush()
    operation(db, compte, "-202", JOUR, REMISE)

    (proposition,) = lire(client, comptable, db).json()["propositions"]
    response = valider(client, comptable, db, (compte, JOUR))

    assert proposition["journal"] == "5541"
    assert response.status_code == 200, response.text
    entry = db.scalar(select(AccountingEntry).filter_by(origine="SIMTIS"))
    assert entry.journal == "5541"
