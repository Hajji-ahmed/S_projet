"""Rapports Excel (P16.4, 14/10/2026). Excel seulement (décision du 14/10/2026), sauf la position
bancaire, aussi en PDF depuis le 27/10/2026 (`position_pdf`, même tableau que l'Excel).

Aucun chiffre n'est recalculé ici :
- « Position du jour » reprend le tableau Banques tel que l'écran le calcule
  (`position_banques_service.banques_table`), dans sa structure : une colonne par banque, TOTAL,
  DEPASSEMENT ; la ligne LIGNE, une ligne « facilité de caisse » par jour, « Disponible Fc reel » ;
  un dernier solde connu repris d'un jour précédent est en italique gris, comme à l'écran ;
- « État de rapprochement » compte les opérations du relevé par statut sur la période, compte par
  compte (chacun dans sa devise, jamais additionnés entre devises), puis liste les opérations qui
  ne sont pas « Rapprochée ».
Le lettrage et les écritures de frais pour Sage gardent leurs exports existants. Chaque export
est audité (`export_rapport`).
"""

from datetime import date
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.models import BankAccount
from app.repositories import account_repository, rapports_repository, reconciliation_repository
from app.services import audit_service, position_banques_service
from app.services.account_service import fraction_to_pct
from app.services.errors import ConflictError, NotFoundError
from app.services.position_service import LigneTableau, business_today

PERIODE_MAX_JOURS = 1827  # 5 ans, comme le lettrage
STATUTS = ("Rapprochée", "À vérifier", "Non rapprochée", "Écart")
FORMAT_MONTANT = "#,##0.00"
FORMAT_DATE = "DD/MM/YYYY"
GRAS = Font(bold=True)
REPRISE = Font(italic=True, color="71839B")
EN_TETE = PatternFill("solid", fgColor="E7F6F4")


def _company(db: Session, company_id: int):
    company = account_repository.get_company(db, company_id)
    if company is None or not company.actif:
        raise NotFoundError("Société introuvable.")
    return company


def _en_tete(sheet: Worksheet, valeurs: list) -> None:
    sheet.append(valeurs)
    for cell in sheet[sheet.max_row]:
        cell.font = GRAS
        cell.fill = EN_TETE


def _largeurs(sheet: Worksheet, largeurs: list[int]) -> None:
    for index, largeur in enumerate(largeurs, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = largeur


def _octets(workbook: Workbook) -> bytes:
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _audit(db, *, rapport: str, company_id: int, acteur_id: int, ip: str | None, **details):
    audit_service.log(
        db,
        user_id=acteur_id,
        action="export_rapport",
        entite="company",
        entite_id=company_id,
        apres={"rapport": rapport, **details},
        ip=ip,
    )
    db.commit()


# --- Position du jour -----------------------------------------------------------------------------


def position_du_jour(
    db: Session, company_id: int, jour: date | None, *, acteur_id: int, ip: str | None
) -> tuple[str, bytes]:
    company = _company(db, company_id)
    tableau = position_banques_service.banques_table(db, company.id, jour)
    banques = tableau.banques

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Banques"
    sheet.append([f"Position bancaire — {company.nom} — au {tableau.date_fin:%d/%m/%Y}"])
    sheet["A1"].font = Font(bold=True, size=13)
    sheet.append([])
    _en_tete(sheet, ["", *(banque.code for banque in banques), "TOTAL", "DEPASSEMENT"])

    sheet.append(["LIGNE", *(banque.ligne for banque in banques), tableau.ligne_total, None])
    sheet[sheet.max_row][0].font = GRAS

    def ligne(libelle, valeur_date, contenu: LigneTableau) -> None:
        sheet.append(
            [
                libelle if valeur_date is None else valeur_date,
                *(cellule.valeur for cellule in contenu.cellules),
                contenu.total,
                contenu.depassement,
            ]
        )
        row = sheet[sheet.max_row]
        for index, cellule in enumerate(contenu.cellules, start=1):
            if cellule.reprise:
                row[index].font = REPRISE

    sheet.append(["facilité de caisse"])
    sheet[sheet.max_row][0].font = GRAS
    for jour_tableau in tableau.jours:
        ligne(None, jour_tableau.date, jour_tableau.ligne)
    ligne("Disponible Fc reel", None, tableau.disponible)
    sheet[sheet.max_row][0].font = GRAS

    for row in sheet.iter_rows(min_row=4):
        if isinstance(row[0].value, date):
            row[0].number_format = FORMAT_DATE
        for cell in row[1:]:
            cell.number_format = FORMAT_MONTANT
    _largeurs(sheet, [20, *([16] * len(banques)), 18, 18])
    sheet.freeze_panes = "B4"
    contenu = _octets(workbook)

    _audit(
        db,
        rapport="position_du_jour",
        company_id=company.id,
        acteur_id=acteur_id,
        ip=ip,
        date=tableau.date_fin,
        jours=len(tableau.jours),
    )
    return f"position-{company.code}-{tableau.date_fin:%Y%m%d}.xlsx".lower(), contenu


# --- État de rapprochement ------------------------------------------------------------------------


# --- Position du jour en PDF (27/10/2026) ---------------------------------------------------------

# Couleurs du thème SIMTIS (frontend/app/globals.css)
PDF_PRIMAIRE = colors.HexColor("#004F54")
PDF_EN_TETE = colors.HexColor("#E7F6F4")
PDF_GRILLE = colors.HexColor("#D5E3E6")
PDF_REPRISE = colors.HexColor("#71839B")
PDF_POSITIF = colors.HexColor("#15803D")
PDF_NEGATIF = colors.HexColor("#B91C1C")


def montant_pdf(valeur: Decimal | None) -> str:
    """« -1234567.8 » → « -1 234 567,80 » ; vide pour une valeur inconnue, jamais 0."""
    if valeur is None:
        return ""
    texte = f"{abs(valeur):,.2f}".replace(",", " ").replace(".", ",")
    return f"-{texte}" if valeur < 0 else texte


def _taux_pdf(taux: Decimal | None) -> str:
    pct = fraction_to_pct(taux)
    if pct is None:
        return "-"
    entier, _, decimales = format(pct, "f").partition(".")
    return f"{entier},{decimales.ljust(2, '0')} %"


def position_pdf(
    db: Session, company_id: int, jour: date | None, *, acteur_id: int, ip: str | None
) -> tuple[str, bytes]:
    """Tableau Banques de l'écran Position bancaire en PDF A4 paysage, dans sa structure imposée :
    Taux, LIGNE, une ligne « facilité de caisse » par jour, Disponible Fc reel ; une colonne par
    banque, TOTAL, DEPASSEMENT. Un dernier solde connu repris d'un jour précédent est en italique
    gris, comme à l'écran ; l'en-tête des colonnes se répète sur chaque page."""
    company = _company(db, company_id)
    tableau = position_banques_service.banques_table(db, company.id, jour)
    banques = tableau.banques
    nb = len(banques)

    lignes: list[list[str]] = [["", *(banque.code for banque in banques), "TOTAL", "DEPASSEMENT"]]
    styles: list[tuple] = []
    lignes.append(["Taux", *(_taux_pdf(banque.taux_interet) for banque in banques), "", ""])
    lignes.append(
        [
            "LIGNE",
            *(montant_pdf(banque.ligne) for banque in banques),
            montant_pdf(tableau.ligne_total),
            "",
        ]
    )

    def ajouter(libelle: str, contenu: LigneTableau) -> None:
        rang = len(lignes)
        lignes.append(
            [
                libelle,
                *(montant_pdf(cellule.valeur) for cellule in contenu.cellules),
                montant_pdf(contenu.total),
                montant_pdf(contenu.depassement),
            ]
        )
        for index, cellule in enumerate(contenu.cellules, start=1):
            if cellule.reprise:
                styles.append(("TEXTCOLOR", (index, rang), (index, rang), PDF_REPRISE))
                styles.append(("FONTNAME", (index, rang), (index, rang), "Helvetica-Oblique"))

    for jour_tableau in tableau.jours:
        ajouter(f"facilité de caisse {jour_tableau.date:%d/%m/%y}", jour_tableau.ligne)
    rang_disponible = len(lignes)
    ajouter("Disponible Fc reel", tableau.disponible)
    disponibles = [*(c.valeur for c in tableau.disponible.cellules), tableau.disponible.total]
    for index, valeur in enumerate(disponibles, start=1):
        if valeur:
            couleur = PDF_POSITIF if valeur > 0 else PDF_NEGATIF
            styles.append(
                ("TEXTCOLOR", (index, rang_disponible), (index, rang_disponible), couleur)
            )

    largeur_libelle = 48 * mm
    largeur_montant = min(32 * mm, (landscape(A4)[0] - 20 * mm - largeur_libelle) / (nb + 2))
    table = Table(
        lignes, colWidths=[largeur_libelle, *([largeur_montant] * (nb + 2))], repeatRows=1
    )
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BACKGROUND", (0, 0), (-1, 0), PDF_EN_TETE),
                ("TEXTCOLOR", (0, 0), (-1, 0), PDF_PRIMAIRE),
                ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (0, rang_disponible), (-1, rang_disponible), "Helvetica-Bold"),
                ("BACKGROUND", (0, rang_disponible), (-1, rang_disponible), PDF_EN_TETE),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.4, PDF_GRILLE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                *styles,
            ]
        )
    )

    feuille = getSampleStyleSheet()
    titre = feuille["Title"].clone("titre", textColor=PDF_PRIMAIRE, fontSize=14, alignment=0)
    note = feuille["Normal"].clone("note", fontSize=7.5, textColor=PDF_REPRISE)
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"Position bancaire {company.nom} au {tableau.date_fin:%d/%m/%Y}",
        author="SIMTIS Finance",
    )
    document.build(
        [
            Paragraph(f"Position bancaire — {company.nom} — au {tableau.date_fin:%d/%m/%Y}", titre),
            Paragraph(
                f"Édité le {business_today():%d/%m/%Y}. Montants en DH, comptes courants MAD. "
                "En italique gris : dernier solde connu repris d'un jour précédent.",
                note,
            ),
            Spacer(1, 4 * mm),
            table,
        ]
    )

    _audit(
        db,
        rapport="position_du_jour_pdf",
        company_id=company.id,
        acteur_id=acteur_id,
        ip=ip,
        date=tableau.date_fin,
        jours=len(tableau.jours),
    )
    return f"position-{company.code}-{tableau.date_fin:%Y%m%d}.pdf".lower(), buffer.getvalue()


def _periode(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    today = business_today()
    date_to = min(date_to or today, today)
    date_from = date_from or date_to.replace(day=1)
    if date_from > date_to:
        raise ConflictError("La date de début doit précéder la date de fin.")
    if (date_to - date_from).days >= PERIODE_MAX_JOURS:
        raise ConflictError("La période ne peut pas dépasser 5 ans.")
    return date_from, date_to


def _nom_compte(account: BankAccount) -> str:
    return f"{account.bank.code} · {account.numero} · {account.devise}"


def etat_rapprochement(
    db: Session,
    company_id: int,
    date_from: date | None,
    date_to: date | None,
    *,
    acteur_id: int,
    ip: str | None,
) -> tuple[str, bytes]:
    company = _company(db, company_id)
    date_from, date_to = _periode(date_from, date_to)
    comptes = sorted(
        reconciliation_repository.company_accounts(db, company.id),
        key=lambda a: (a.bank.ordre_affichage, a.devise, a.id),
    )
    ids = [account.id for account in comptes]
    par_compte = rapports_repository.statuts_par_compte(db, ids, date_from, date_to)

    workbook = Workbook()
    synthese = workbook.active
    synthese.title = "Synthèse"
    synthese.append(
        [f"État de rapprochement — {company.nom} — du {date_from:%d/%m/%Y} au {date_to:%d/%m/%Y}"]
    )
    synthese["A1"].font = Font(bold=True, size=13)
    synthese.append([])
    _en_tete(
        synthese,
        ["Compte", *STATUTS, "Total", "Taux rapproché (%)", "Reste à rapprocher : débit",
         "Reste à rapprocher : crédit"],
    )  # fmt: skip
    for account in comptes:
        statuts = par_compte.get(account.id, {})
        total = sum(nombre for nombre, _, _ in statuts.values())
        if total == 0:
            continue
        rapprochees = statuts.get("Rapprochée", (0, 0, 0))[0]
        reste = [v for s, v in statuts.items() if s != "Rapprochée"]
        synthese.append(
            [
                _nom_compte(account),
                *(statuts.get(statut, (0, 0, 0))[0] for statut in STATUTS),
                total,
                (Decimal(rapprochees) * 100 / total).quantize(Decimal("0.1")),
                sum((debit for _, debit, _ in reste), Decimal("0.00")),
                sum((credit for _, _, credit in reste), Decimal("0.00")),
            ]
        )
    for row in synthese.iter_rows(min_row=4):
        row[6].number_format = "0.0"
        row[7].number_format = row[8].number_format = FORMAT_MONTANT
    _largeurs(synthese, [34, 12, 12, 15, 9, 9, 18, 24, 24])
    synthese.freeze_panes = "B4"

    detail = workbook.create_sheet("À rapprocher")
    _en_tete(
        detail,
        ["Compte", "Date d'opération", "Date de valeur", "Libellé", "Référence", "Débit",
         "Crédit", "Statut"],
    )  # fmt: skip
    noms = {account.id: _nom_compte(account) for account in comptes}
    operations = rapports_repository.non_rapprochees(db, ids, date_from, date_to)
    for tx in operations:
        detail.append(
            [noms[tx.bank_account_id], tx.date_operation, tx.date_valeur, tx.libelle,
             tx.reference, tx.debit or None, tx.credit or None, tx.statut]
        )  # fmt: skip
    for row in detail.iter_rows(min_row=2):
        row[1].number_format = row[2].number_format = FORMAT_DATE
        row[5].number_format = row[6].number_format = FORMAT_MONTANT
    _largeurs(detail, [34, 14, 14, 50, 18, 16, 16, 16])
    detail.freeze_panes = "A2"
    contenu = _octets(workbook)

    _audit(
        db,
        rapport="etat_rapprochement",
        company_id=company.id,
        acteur_id=acteur_id,
        ip=ip,
        du=date_from,
        au=date_to,
        operations_a_rapprocher=len(operations),
    )
    nom = f"etat-rapprochement-{company.code}-{date_from:%Y%m%d}-{date_to:%Y%m%d}.xlsx"
    return nom.lower(), contenu
