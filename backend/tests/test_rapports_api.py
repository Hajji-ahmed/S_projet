"""Rapports Excel (P16.4) : position du jour, état de rapprochement, permissions et audit."""

from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from app.models import AuditLog
from app.services import rapports_service
from tests.helpers import bearer, login, make_auth_user
from tests.test_reconciliation_api import account, company, ecriture, operation


@pytest.fixture
def responsable(client, reference):
    make_auth_user(reference, "RESPONSABLE", email="resp@example.com")
    return bearer(login(client, "resp@example.com"))


def classeur(response):
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    return load_workbook(BytesIO(response.content))


def test_the_daily_position_keeps_the_banks_table_structure(client, responsable, db):
    awb = account(db)
    awb.credit_autorise = Decimal("500000.00")
    db.flush()
    operation(db, awb, montant="-200000", jour=date(2026, 9, 1), solde=Decimal("-200000"))

    response = client.get(
        "/api/rapports/position",
        params={"company_id": str(company(db).id), "date": "2026-09-02"},
        headers=responsable,
    )

    sheet = classeur(response)["Banques"]
    rows = [[cell.value for cell in row] for row in sheet.iter_rows()]
    en_tete = rows[2]
    assert en_tete[1:3] == ["AWB", "BMCE"] and en_tete[-2:] == ["TOTAL", "DEPASSEMENT"]
    assert rows[3][0] == "LIGNE" and rows[3][1] == 500000
    assert rows[4][0] == "facilité de caisse"
    # 01/09 : solde du jour (02/11/2026) ; 02/09 : dernier solde connu repris, en italique
    assert rows[5][1] == -200000 and rows[6][1] == -200000
    assert sheet.cell(row=7, column=2).font.italic is True
    # Disponible Fc reel = solde + LIGNE
    assert rows[-1][0] == "Disponible Fc reel" and rows[-1][1] == 300000
    assert "attachment" in response.headers["content-disposition"]
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "export_rapport"))
    assert audit.nouvelle_valeur["rapport"] == "position_du_jour"


def test_the_ligne_row_of_the_excel_position_is_teal_with_a_line_under_it(client, responsable, db):
    awb = account(db)
    awb.credit_autorise = Decimal("500000.00")
    db.flush()
    operation(db, awb, montant="-200000", jour=date(2026, 9, 1), solde=Decimal("-200000"))

    response = client.get(
        "/api/rapports/position",
        params={"company_id": str(company(db).id), "date": "2026-09-02"},
        headers=responsable,
    )

    sheet = classeur(response)["Banques"]
    # Rangée 4 = LIGNE (12/11/2026) : toute la largeur, TOTAL et DEPASSEMENT compris
    for colonne in range(1, sheet.max_column + 1):
        cellule = sheet.cell(row=4, column=colonne)
        assert cellule.fill.fgColor.rgb.endswith("E7F6F4")
        assert cellule.border.bottom.style == "medium"
        assert cellule.border.bottom.color.rgb.endswith("004F54")
    # Les jours restent sans fond
    assert sheet.cell(row=6, column=2).fill.fill_type is None


def rapprocher(client, headers, operations, ecritures, id_seulement=False):
    """Rapprochement manuel validé ; renvoie son code (ou son id)."""
    response = client.post(
        "/api/reconciliation/matches",
        json={
            "transaction_ids": [o.id for o in operations],
            "ecriture_ids": [e.id for e in ecritures],
        },
        headers=headers,
    )
    assert response.status_code in (200, 201), response.text
    return response.json()["id" if id_seulement else "code"]


def test_the_lettrage_can_be_limited_to_one_bank(client, reference, db):
    """04/11/2026 (écran Rapports) : le lettrage de la banque choisie ne garde que ses
    rapprochements validés de la période, opérations puis écritures par code."""
    make_auth_user(reference, "COMPTABLE", email="comptable@example.com")
    comptable = bearer(login(client, "comptable@example.com"))
    bp = account(db, bank_code="BP")
    awb = account(db, bank_code="AWB")
    chq = operation(db, bp, montant="-1200", jour=date(2026, 9, 3), libelle="CHQ 0173813")
    e_chq = ecriture(db, bp, montant="1200", jour=date(2026, 9, 3), libelle="EAR1 173813")
    vir = operation(db, bp, montant="3000", jour=date(2026, 9, 10), libelle="VIR KARIM")
    e1 = ecriture(db, bp, montant="-1000", jour=date(2026, 9, 10), libelle="REG KARIM 1")
    e2 = ecriture(db, bp, montant="-2000", jour=date(2026, 9, 11), libelle="REG KARIM 2")
    hors = operation(db, bp, montant="500", jour=date(2026, 10, 2), libelle="HORS PERIODE")
    e_hors = ecriture(db, bp, montant="-500", jour=date(2026, 10, 2))
    autre = operation(db, awb, montant="700", jour=date(2026, 9, 5), libelle="AUTRE BANQUE")
    e_autre = ecriture(db, awb, montant="-700", jour=date(2026, 9, 5))
    annule = operation(db, bp, montant="900", jour=date(2026, 9, 20), libelle="ANNULE")
    e_annule = ecriture(db, bp, montant="-900", jour=date(2026, 9, 20))
    code_chq = rapprocher(client, comptable, [chq], [e_chq])
    code_vir = rapprocher(client, comptable, [vir], [e1, e2])
    rapprocher(client, comptable, [hors], [e_hors])
    rapprocher(client, comptable, [autre], [e_autre])
    match_annule = rapprocher(client, comptable, [annule], [e_annule], id_seulement=True)
    assert (
        client.request(
            "DELETE",
            f"/api/reconciliation/matches/{match_annule}",
            json={"motif": "erreur"},
            headers=comptable,
        ).status_code
        == 200
    )

    response = client.get(
        "/api/reconciliation/export",
        params={
            "company_id": str(company(db).id),
            "from": "2026-09-01",
            "to": "2026-09-30",
            "bank_id": str(bp.bank_id),
        },
        headers=comptable,
    )

    workbook = classeur(response)
    assert len(workbook.sheetnames) == 1
    feuille = workbook.worksheets[0]
    # Comptabilité à gauche, banque à droite (07/11/2026)
    assert feuille.cell(row=3, column=3).value == "Comptabilité"
    assert feuille.cell(row=3, column=10).value == "Banque"
    assert [c.value for c in feuille[4]] == [
        "Code", "Validé le", "Date", "N° pièce", "Libellé", "Débit (DH)", "Crédit (DH)",
        "Échéance", None, "Date", "Libellé", "Réf.", "Débit (DH)", "Crédit (DH)",
    ]  # fmt: skip
    lignes = [list(r) for r in feuille.iter_rows(min_row=5, values_only=True)]
    # Le chèque face à son écriture ; le virement face à la 1re écriture, la 2e seule
    assert [(r[0], r[4], r[8], r[10]) for r in lignes[:-1]] == [
        (code_chq, "EAR1 173813", "⇄", "CHQ 0173813"),
        (code_vir, "REG KARIM 1", "⇄", "VIR KARIM"),
        (None, "REG KARIM 2", None, None),
    ]
    total = lignes[-1]
    assert total[0] == "Total"
    # Débit / crédit comptabilité, puis débit / crédit banque
    assert (total[5], total[6], total[12], total[13]) == (3000, 1200, 1200, 3000)
    assert feuille.cell(row=6, column=1).fill.fgColor.rgb.endswith("F5F8FA")
    assert "lettrage-BP-2026-09-01-2026-09-30.xlsx" in response.headers["content-disposition"]
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "export_lettrage"))
    assert audit.nouvelle_valeur["banque"] == bp.bank_id

    # Sans banque : l'autre banque est dans le lettrage
    toutes = client.get(
        "/api/reconciliation/export",
        params={"company_id": str(company(db).id), "from": "2026-09-01", "to": "2026-09-30"},
        headers=comptable,
    )
    feuilles = classeur(toutes).worksheets
    libelles = [r[10] for f in feuilles for r in f.iter_rows(min_row=5, values_only=True)]
    assert len(feuilles) == 2
    assert "AUTRE BANQUE" in libelles


def test_reports_check_the_period_and_their_permissions(client, reference, db):
    make_auth_user(reference, "TRESORERIE", email="treso@example.com")
    treso = bearer(login(client, "treso@example.com"))
    societe = str(company(db).id)

    # Trésorerie consulte la position et le rapprochement (rôle de consultation)
    assert (
        client.get(
            "/api/rapports/position", params={"company_id": societe}, headers=treso
        ).status_code
        == 200
    )
    assert (
        client.get(
            "/api/rapports/non-rapproches",
            params={"company_id": societe, "from": "2026-09-30", "to": "2026-09-01"},
            headers=treso,
        ).status_code
        == 409
    )

    make_auth_user(reference, email="sansrole@example.com")
    aucun = bearer(login(client, "sansrole@example.com"))
    assert (
        client.get(
            "/api/rapports/position", params={"company_id": societe}, headers=aucun
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/rapports/non-rapproches", params={"company_id": societe}, headers=aucun
        ).status_code
        == 403
    )


# --- Position bancaire en PDF (27/10/2026) --------------------------------------------------------


def test_the_daily_position_is_also_given_as_a_pdf(client, responsable, db):
    awb = account(db)
    awb.credit_autorise = Decimal("500000.00")
    db.flush()
    operation(db, awb, montant="-200000", jour=date(2026, 9, 1), solde=Decimal("-200000"))

    response = client.get(
        "/api/rapports/position/pdf",
        params={"company_id": str(company(db).id), "date": "2026-09-02"},
        headers=responsable,
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert 'filename="position-simtis-20260902.pdf"' in response.headers["content-disposition"]
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "export_rapport"))
    assert audit.nouvelle_valeur["rapport"] == "position_du_jour_pdf"


def test_the_pdf_rate_and_ligne_rows_are_teal_with_a_line_under_ligne(
    client, responsable, db, monkeypatch
):
    awb = account(db)
    awb.credit_autorise = Decimal("500000.00")
    db.flush()
    operation(db, awb, montant="-200000", jour=date(2026, 9, 1), solde=Decimal("-200000"))
    commandes: list[tuple] = []
    original = rapports_service.TableStyle

    def espion(cmds, *args, **kwargs):
        commandes.extend(cmds)
        return original(cmds, *args, **kwargs)

    monkeypatch.setattr(rapports_service, "TableStyle", espion)

    response = client.get(
        "/api/rapports/position/pdf",
        params={"company_id": str(company(db).id), "date": "2026-09-02"},
        headers=responsable,
    )

    assert response.status_code == 200, response.text
    # Rangées 1 (Taux) et 2 (LIGNE), 12/11/2026 : fond teal clair, trait teal sous LIGNE
    assert ("BACKGROUND", (0, 1), (-1, 2), rapports_service.PDF_EN_TETE) in commandes
    trait = ("LINEBELOW", (0, 2), (-1, 2), 1, rapports_service.PDF_PRIMAIRE)
    assert trait in commandes
    # Le trait est dessiné après la grille, donc par-dessus
    grille = next(i for i, c in enumerate(commandes) if c[0] == "GRID")
    assert commandes.index(trait) > grille
    # Les jours (rangées 3 et 4) restent sans fond
    fonds = [c for c in commandes if c[0] == "BACKGROUND"]
    assert all(not ({3, 4} & set(range(c[1][1], c[2][1] + 1))) for c in fonds)


def test_the_pdf_position_needs_the_position_permission(client, reference, db):
    make_auth_user(reference, email="sansrole@example.com")
    aucun = bearer(login(client, "sansrole@example.com"))

    response = client.get(
        "/api/rapports/position/pdf", params={"company_id": str(company(db).id)}, headers=aucun
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("valeur", "texte"),
    [
        (Decimal("-1234567.8"), "-1 234 567,80"),
        (Decimal("0"), "0,00"),
        (Decimal("950.5"), "950,50"),
        (None, ""),
    ],
)
def test_pdf_amounts_are_written_the_french_way(valeur, texte):
    from app.services.rapports_service import montant_pdf

    assert montant_pdf(valeur) == texte


# --- Lignes non rapprochées (30/10/2026) ----------------------------------------------------------


def lignes(feuille, colonne: int) -> list[str]:
    """Libellés d'un côté de la feuille (colonne 2 = Sage, 10 = relevé, depuis le 07/11/2026), sous l'en-tête et la
    ligne des soldes, jusqu'au total."""
    valeurs = []
    for row in feuille.iter_rows(min_row=5, values_only=True):
        if row[0] == "Total" or row[colonne - 2] == "Total":
            break
        valeurs.append(row[colonne - 1])
    return [v for v in valeurs if v not in (None, "Total") and not isinstance(v, (int, float))]


def test_unreconciled_lines_side_by_side_for_one_bank_and_period(client, responsable, db):
    bp = account(db, bank_code="BP")
    awb = account(db, bank_code="AWB")
    operation(db, bp, montant="9000", jour=date(2026, 9, 30), libelle="VERSEMENT DEPLACE PAR X")
    operation(db, bp, montant="-25", jour=date(2026, 9, 29), libelle="COMMISSION")
    propose = operation(db, bp, montant="1200", jour=date(2026, 9, 28), libelle="VIR KARIM")
    propose.statut = "À vérifier"
    rapprochee = operation(db, bp, montant="500", jour=date(2026, 9, 27), libelle="VIR RAPPROCHE")
    rapprochee.statut = "Rapprochée"
    en_cours = operation(db, bp, montant="700", jour=date(2026, 9, 26), libelle="VIR SRBM (*)")
    en_cours.en_cours = True
    operation(db, bp, montant="800", jour=date(2026, 8, 15), libelle="HORS PERIODE")
    operation(db, awb, montant="900", jour=date(2026, 9, 30), libelle="AUTRE BANQUE")
    ecriture(db, bp, montant="-9000", jour=date(2026, 9, 30), libelle="ESP TT26272F48TV")
    db.flush()

    response = client.get(
        "/api/rapports/non-rapproches",
        params={
            "company_id": str(company(db).id),
            "from": "2026-09-01",
            "to": "2026-09-30",
            "bank_id": str(bp.bank_id),
        },
        headers=responsable,
    )

    workbook = classeur(response)
    assert len(workbook.sheetnames) == 1
    feuille = workbook[workbook.sheetnames[0]]
    # Comptabilité à gauche (A–G, échéance en F), relevé à droite (I–N) (07/11/2026)
    assert feuille.cell(row=2, column=1).value == "Écritures comptables (1)"
    # Côté Sage, N° pièce juste avant l'échéance (10/11/2026) ; côté relevé inchangé
    titres = [c.value for c in feuille[3]]
    assert titres[:7] == [
        "Date", "Libellé", "Débit (DH)", "Crédit (DH)", "Pce", "Échéance", "St.",
    ]  # fmt: skip
    assert titres[8:] == ["Date", "Libellé", "Réf.", "Débit (DH)", "Crédit (DH)", "St."]
    assert feuille.cell(row=2, column=9).value == "Transactions bancaires (3)"
    # Du plus ancien au plus récent (02/11/2026), rapprochées, en cours et hors période exclues
    assert lignes(feuille, 10) == ["VIR KARIM", "COMMISSION", "VERSEMENT DEPLACE PAR X"]
    statuts = [row[13] for row in feuille.iter_rows(min_row=5, max_row=7, values_only=True)]
    assert statuts == ["En proposition", "Non rapprochée · frais", "Non rapprochée"]
    assert feuille.cell(row=5, column=2).value == "ESP TT26272F48TV"
    assert (
        "etat-rapprochement-simtis-bp-2026-09-01-2026-09-30.xlsx"
        in (response.headers["content-disposition"])
    )
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "export_rapport"))
    assert audit.nouvelle_valeur["rapport"] == "non_rapproches"


def test_unreconciled_lines_need_the_reconciliation_permission(client, reference, db):
    make_auth_user(reference, email="sansrole@example.com")
    aucun = bearer(login(client, "sansrole@example.com"))

    response = client.get(
        "/api/rapports/non-rapproches", params={"company_id": str(company(db).id)}, headers=aucun
    )

    assert response.status_code == 403


# --- Soldes et contrôle des lignes non rapprochées (02/11/2026) -----------------------------------


def non_rapproches(client, headers, db, compte, du="2026-09-01", au="2026-09-30"):
    return client.get(
        "/api/rapports/non-rapproches",
        params={"company_id": str(company(db).id), "from": du, "to": au, "bank_id": compte.bank_id},
        headers=headers,
    )


def test_unreconciled_lines_start_with_both_balances_and_end_at_zero(client, responsable, db):
    bp = account(db, bank_code="BP")
    bp.date_solde_comptable = date(2026, 8, 31)
    bp.solde_comptable_ouverture = Decimal("1000.00")
    paye = operation(db, bp, montant="500", jour=date(2026, 9, 10), solde=Decimal("1500"))
    paye.statut = "Rapprochée"
    operation(db, bp, montant="9000", jour=date(2026, 9, 30), libelle="VERSEMENT X",
              solde=Decimal("10500"))  # fmt: skip
    # Sage : débit = entrée en banque ; la 2e écriture n'est pas encore au relevé
    lettree = ecriture(db, bp, montant="-500", jour=date(2026, 9, 10))
    lettree.statut = "Rapprochée"
    esp = ecriture(db, bp, montant="-200", jour=date(2026, 9, 29), libelle="ESP Y")
    esp.echeance = date(2026, 10, 15)
    esp.numero_piece = "BP2609001"
    db.flush()

    feuille = classeur(non_rapproches(client, responsable, db, bp)).active

    # Solde du relevé créditeur (Crédit), solde comptable débiteur dans Sage (Débit)
    assert feuille.cell(row=4, column=2).value == "Solde comptable au 30/09/2026"
    assert feuille.cell(row=4, column=3).value == 1700
    assert feuille.cell(row=4, column=10).value == "Solde du relevé au 30/09/2026"
    assert feuille.cell(row=4, column=13).value == 10500
    assert lignes(feuille, 2) == ["ESP Y"]
    assert feuille.cell(row=5, column=6).value.date() == date(2026, 10, 15)  # échéance
    assert feuille.cell(row=5, column=5).value == "BP2609001"  # N° pièce juste avant
    assert feuille.cell(row=5, column=3).value == 200  # Débit
    assert lignes(feuille, 10) == ["VERSEMENT X"]
    # Solde compta avant Solde banque à l'affichage (07/11/2026), même calcul
    controle = [(r[1], r[2]) for r in feuille.iter_rows(min_row=10, max_row=12, values_only=True)]
    assert controle == [
        ("Solde compta", 10700),
        ("Solde banque", 10700),
        ("Écart", 0),
    ]


def test_without_accounting_opening_the_balance_is_not_invented(client, responsable, db):
    bp = account(db, bank_code="BP")
    operation(db, bp, montant="9000", jour=date(2026, 9, 30), solde=Decimal("9000"))
    db.flush()

    feuille = classeur(non_rapproches(client, responsable, db, bp)).active

    assert feuille.cell(row=4, column=7).value == "non renseigné"
    assert feuille.cell(row=4, column=3).value is None
    valeurs = {r[1]: r[2] for r in feuille.iter_rows(min_row=9, values_only=True) if r[1]}
    assert valeurs["Écart"] == "non calculable"
    assert valeurs["Solde banque"] == 9000


def test_unreconciled_lines_cover_up_to_ten_years(client, responsable, db):
    bp = account(db, bank_code="BP")
    operation(db, bp, montant="10", jour=date(2017, 1, 20))
    db.flush()

    neuf_ans = non_rapproches(client, responsable, db, bp, du="2017-01-20", au="2026-09-30")
    onze_ans = non_rapproches(client, responsable, db, bp, du="2015-09-01", au="2026-09-30")

    assert lignes(classeur(neuf_ans).active, 10) == ["VIR ABC"]
    assert onze_ans.status_code == 409
    assert onze_ans.json()["detail"] == "La période ne peut pas dépasser 10 ans."


# --- Rapprochements à cheval sur « Au » (07/11/2026) ----------------------------------------------


@pytest.fixture
def comptable(client, reference):
    make_auth_user(reference, "COMPTABLE", email="comptable@example.com")
    return bearer(login(client, "comptable@example.com"))


def controle(feuille) -> dict:
    return {r[1]: r[2] for r in feuille.iter_rows(min_row=5, values_only=True) if r[1]}


def test_a_match_closed_after_the_end_date_is_still_pending_at_that_date(
    client, responsable, comptable, db
):
    """Cas AWB-26-000025 : virement au relevé le 28/09, saisi dans Sage le 01/10. Au 30/09 il est
    en suspens (listé, écart 0) ; au 01/10 il est rapproché (rien à lister)."""
    bp = account(db, bank_code="BP")
    bp.date_solde_comptable = date(2026, 8, 31)
    bp.solde_comptable_ouverture = Decimal("1000.00")
    vir = operation(db, bp, montant="10000", jour=date(2026, 9, 28), libelle="VIR EL BRINSSI",
                    solde=Decimal("11000"))  # fmt: skip
    sage = ecriture(db, bp, montant="-10000", jour=date(2026, 10, 1), libelle="VIR 4000585157")
    db.flush()
    rapprocher(client, comptable, [vir], [sage])

    au_30 = classeur(non_rapproches(client, responsable, db, bp)).active

    assert lignes(au_30, 10) == ["VIR EL BRINSSI"]
    assert lignes(au_30, 14) == ["Rapprochée le 01/10/26"]
    assert lignes(au_30, 2) == []
    valeurs = controle(au_30)
    assert (valeurs["Solde banque"], valeurs["Solde compta"], valeurs["Écart"]) == (
        11000,
        11000,
        0,
    )

    au_01 = classeur(non_rapproches(client, responsable, db, bp, au="2026-10-01")).active
    assert au_01.title == "État de rapprochement"


def test_an_entry_matched_with_a_later_operation_is_listed(client, responsable, comptable, db):
    bp = account(db, bank_code="BP")
    bp.date_solde_comptable = date(2026, 8, 31)
    bp.solde_comptable_ouverture = Decimal("0.00")
    # Rapprochement entièrement dans la période : jamais listé
    chq = operation(db, bp, montant="-300", jour=date(2026, 9, 5), libelle="CHQ 1",
                    solde=Decimal("-300"))  # fmt: skip
    e_chq = ecriture(db, bp, montant="300", jour=date(2026, 9, 5), libelle="EAR CHQ 1")
    esp = ecriture(db, bp, montant="-5000", jour=date(2026, 9, 30), libelle="ESP 56203522")
    depot = operation(db, bp, montant="5000", jour=date(2026, 10, 2), libelle="VERSEMENT ESPECE",
                      solde=Decimal("4700"))  # fmt: skip
    db.flush()
    rapprocher(client, comptable, [chq], [e_chq])
    rapprocher(client, comptable, [depot], [esp])

    feuille = classeur(non_rapproches(client, responsable, db, bp)).active

    assert lignes(feuille, 10) == []
    assert lignes(feuille, 2) == ["ESP 56203522"]
    assert lignes(feuille, 7) == ["Rapprochée le 02/10/26"]
    assert controle(feuille)["Écart"] == 0


@pytest.mark.parametrize(
    ("releve", "comptable", "attendu"),
    [
        ("-969604.15", "-3202420.03", ["-7936707.88", "-7936707.88", "0.00"]),
        (None, "100.00", [None, "-4734187.85", None]),
    ],
)
def test_reconciliation_control_rule(releve, comptable, attendu):
    from app.services.rapports_service import etat_controle

    resultat = etat_controle(
        None if releve is None else Decimal(releve),
        Decimal(comptable),
        Decimal("-4734287.85"),
        Decimal("-6967103.73"),
    )

    assert [None if v is None else str(v) for _, v in resultat] == attendu
