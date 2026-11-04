"""Rapports Excel (P16.4, 14/10/2026). Excel seulement (décision du 14/10/2026), sauf la position
bancaire, aussi en PDF depuis le 27/10/2026 (`position_pdf`, même tableau que l'Excel).

Aucun chiffre n'est recalculé ici :
- « Position du jour » reprend le tableau Banques tel que l'écran le calcule
  (`position_banques_service.banques_table`), dans sa structure : une colonne par banque, TOTAL,
  DEPASSEMENT ; la ligne LIGNE, une ligne « facilité de caisse » par jour, « Disponible Fc reel » ;
  un dernier solde connu repris d'un jour précédent est en italique gris, comme à l'écran ;
- « État de rapprochement » (« Lignes non rapprochées » jusqu'au 04/11/2026, 30/10/2026) met côte
  à côte, compte par compte, les opérations du relevé et les écritures Sage pas encore rapprochées
  de la période, comme l'écran Rapprochement, entre les deux soldes et le contrôle. L'ancien état
  des rapprochements validés côte à côte a été retiré le 04/11/2026 : le lettrage le remplace.
Le lettrage et les écritures de frais pour Sage gardent leurs exports existants. Chaque export
est audité (`export_rapport`).
"""

from datetime import date
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.models import AccountingEntry, BankAccount, BankTransaction
from app.repositories import account_repository, rapports_repository, reconciliation_repository
from app.services import audit_service, position_banques_service, solde_comptable_service
from app.services.account_service import fraction_to_pct
from app.services.errors import ConflictError, NotFoundError
from app.services.position_service import LigneTableau, business_today
from app.services.reconciliation_service import montant_rapprochement
from app.services.solde_comptable_service import SoldeComptable

PERIODE_MAX_JOURS = 1827  # 5 ans, comme le lettrage
NON_RAPPROCHES_MAX_JOURS = 3653  # 10 ans pour l'état de rapprochement (02/11/2026)
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


def _periode(
    date_from: date | None,
    date_to: date | None,
    max_jours: int = PERIODE_MAX_JOURS,
    max_texte: str = "5 ans",
) -> tuple[date, date]:
    today = business_today()
    date_to = min(date_to or today, today)
    date_from = date_from or date_to.replace(day=1)
    if date_from > date_to:
        raise ConflictError("La date de début doit précéder la date de fin.")
    if (date_to - date_from).days >= max_jours:
        raise ConflictError(f"La période ne peut pas dépasser {max_texte}.")
    return date_from, date_to


# --- État de rapprochement : lignes non rapprochées (30/10/2026) ----------------------------------

PROPOSITION = PatternFill("solid", fgColor="FEF3C7")
TITRE = Font(bold=True, size=13, color="004F54")
SOUS_TITRE = Font(bold=True, size=12, color="004F54")
EN_TETE_ECRAN = Font(bold=True, color="004F54")
TRAIT = Border(bottom=Side(style="thin", color="D9E3E8"))
COLONNES_RELEVE = (("Date", 10), ("Libellé", 52), ("Réf.", 14), ("Débit", 15), ("Crédit", 15),
                   ("St.", 18))  # fmt: skip
COLONNES_SAGE = (("Date", 10), ("Libellé", 52), ("Pce", 18), ("Débit", 15), ("Crédit", 15),
                 ("St.", 18))  # fmt: skip
DEBUT_SAGE = len(COLONNES_RELEVE) + 2


def statut_affiche(statut: str, frais: bool = False) -> str:
    """« À vérifier » se lit « En proposition » comme à l'écran ; un frais est signalé."""
    texte = "En proposition" if statut == "À vérifier" else statut
    return f"{texte} · frais" if frais else texte


def _feuille_compte(
    sheet: Worksheet,
    compte: BankAccount,
    operations: list[BankTransaction],
    ecritures: list[AccountingEntry],
    frais_ids: set[int],
    date_from: date,
    date_to: date,
    soldes: SoldeComptable,
) -> None:
    sheet.sheet_view.showGridLines = False
    unite = "DH" if compte.devise == "MAD" else compte.devise
    sheet.cell(
        row=1,
        column=1,
        value=f"{compte.company.nom} · {compte.bank.code} · {compte.devise} · {compte.numero} — "
        f"état de rapprochement du {date_from:%d/%m/%Y} au {date_to:%d/%m/%Y}",
    ).font = TITRE
    sheet.cell(
        row=2, column=1, value=f"Transactions bancaires ({len(operations)})"
    ).font = SOUS_TITRE
    sheet.cell(
        row=2, column=DEBUT_SAGE, value=f"Écritures comptables ({len(ecritures)})"
    ).font = SOUS_TITRE
    for debut, colonnes in ((1, COLONNES_RELEVE), (DEBUT_SAGE, COLONNES_SAGE)):
        for index, (titre, largeur) in enumerate(colonnes):
            montant = titre in ("Débit", "Crédit")
            cellule = sheet.cell(
                row=3, column=debut + index, value=f"{titre} ({unite})" if montant else titre
            )
            cellule.font = EN_TETE_ECRAN
            cellule.fill = EN_TETE
            cellule.alignment = Alignment(horizontal="right" if montant else "left")
            sheet.column_dimensions[get_column_letter(debut + index)].width = largeur
    sheet.column_dimensions[get_column_letter(len(COLONNES_RELEVE) + 1)].width = 3
    sheet.freeze_panes = "A4"

    def ligne(rang: int, debut: int, valeurs: list, proposition: bool) -> None:
        for index, valeur in enumerate(valeurs):
            cellule = sheet.cell(row=rang, column=debut + index, value=valeur)
            cellule.border = TRAIT
            if index == 0:
                cellule.number_format = "DD/MM/YY"
            elif index in (3, 4):
                cellule.number_format = FORMAT_MONTANT
            if proposition:
                cellule.fill = PROPOSITION

    # Soldes au « Au » en tête de chaque côté (02/11/2026), dans la colonne de leur sens :
    # relevé débiteur (négatif) au Débit ; Sage débiteur (positif) au Débit
    banque = soldes.solde_bancaire
    compta = soldes.solde if compte.devise == "MAD" else soldes.solde_devise
    for debut, libelle, solde, debit_si_negatif in (
        (1, "Solde du relevé", banque, True),
        (DEBUT_SAGE, "Solde comptable", compta, False),
    ):
        sheet.cell(row=4, column=debut, value=date_to).number_format = "DD/MM/YY"
        sheet.cell(row=4, column=debut + 1, value=f"{libelle} au {date_to:%d/%m/%Y}")
        if solde is None:
            sheet.cell(row=4, column=debut + 5, value="non renseigné")
        elif solde != 0:
            au_debit = (solde < 0) == debit_si_negatif
            cellule = sheet.cell(row=4, column=debut + (3 if au_debit else 4), value=abs(solde))
            cellule.number_format = FORMAT_MONTANT
        for index in range(len(COLONNES_RELEVE)):
            cellule = sheet.cell(row=4, column=debut + index)
            cellule.font = GRAS
            cellule.fill = EN_TETE
            cellule.border = TRAIT

    for rang, op in enumerate(operations, start=5):
        ligne(
            rang,
            1,
            [
                op.date_operation,
                op.libelle,
                op.reference,
                op.debit or None,
                op.credit or None,
                statut_affiche(op.statut, op.id in frais_ids),
            ],
            op.statut == "À vérifier",
        )
    for rang, ec in enumerate(ecritures, start=5):
        ligne(
            rang,
            DEBUT_SAGE,
            [
                ec.date_ecriture,
                ec.libelle,
                ec.numero_piece,
                ec.debit or None,
                ec.credit or None,
                statut_affiche(ec.statut),
            ],
            ec.statut == "À vérifier",
        )
    fin = 5 + max(len(operations), len(ecritures)) + 1
    for debut, lignes in ((1, operations), (DEBUT_SAGE, ecritures)):
        sheet.cell(row=fin, column=debut, value="Total").font = GRAS
        for decalage, champ in ((3, "debit"), (4, "credit")):
            total = sum((getattr(x, champ) for x in lignes), Decimal("0"))
            cellule = sheet.cell(row=fin, column=debut + decalage, value=total)
            cellule.font = GRAS
            cellule.number_format = FORMAT_MONTANT

    controle = etat_controle(
        banque,
        compta,
        sum((op.montant for op in operations), Decimal("0")),
        # Une écriture Sage au débit est une entrée en banque : vue du relevé, −montant
        sum((-montant_rapprochement(ec) for ec in ecritures), Decimal("0")),
    )
    rang = fin + 2
    sheet.cell(
        row=rang, column=1, value=f"Contrôle au {date_to:%d/%m/%Y} (en {unite}, signe du relevé)"
    ).font = SOUS_TITRE
    for libelle, valeur in controle:
        rang += 1
        sheet.cell(row=rang, column=2, value=libelle).font = GRAS
        cellule = sheet.cell(
            row=rang, column=4, value="non calculable" if valeur is None else valeur
        )
        cellule.font = GRAS
        cellule.number_format = FORMAT_MONTANT
    sheet.cell(
        row=rang + 1,
        column=2,
        value=f"Les lignes datées avant le {date_from:%d/%m/%Y} ne sont pas listées : l'écart "
        "n'est complet que si « Du » couvre tout l'historique du compte.",
    ).font = Font(italic=True, color="5F6B73")


def etat_controle(
    solde_releve: Decimal | None,
    solde_comptable: Decimal | None,
    operations: Decimal,
    ecritures: Decimal,
) -> list[tuple[str, Decimal | None]]:
    """Règle pure de l'état de rapprochement, tout dans le signe du relevé (crédit − débit) :
    solde banque rectifié = solde du relevé + écritures non rapprochées ;
    solde compta rectifié = solde comptable + opérations non rapprochées ; écart = banque − compta
    (0 quand tout est expliqué). Un solde inconnu rend son côté et l'écart non calculables."""
    banque = None if solde_releve is None else solde_releve + ecritures
    compta = None if solde_comptable is None else solde_comptable + operations
    ecart = None if banque is None or compta is None else banque - compta
    return [
        ("Solde banque", banque),
        ("Solde compta", compta),
        ("Écart", ecart),
    ]


def _comptes(db: Session, company_id: int, bank_id: int | None) -> list[BankAccount]:
    """Comptes de la société (ceux d'une banque, si elle est donnée), dans l'ordre des banques."""
    comptes = sorted(
        (
            account
            for account in reconciliation_repository.company_accounts(db, company_id)
            if bank_id is None or account.bank_id == bank_id
        ),
        key=lambda a: (a.bank.ordre_affichage, a.devise, a.id),
    )
    if bank_id is not None and not comptes:
        raise NotFoundError("Aucun compte de cette banque pour la société.")
    return comptes


def _nom_feuille(compte: BankAccount, pris: set[str]) -> str:
    base = f"{compte.bank.code} {compte.devise} {compte.numero[-4:]}"
    nom, suite = base[:31], 2
    while nom in pris:
        nom, suite = f"{base[:27]} {suite}", suite + 1
    pris.add(nom)
    return nom


def non_rapproches(
    db: Session,
    company_id: int,
    date_from: date | None,
    date_to: date | None,
    bank_id: int | None,
    *,
    acteur_id: int,
    ip: str | None,
) -> tuple[str, bytes]:
    """Opérations et écritures non rapprochées de la période, une feuille par compte, côte à côte
    comme l'écran Rapprochement (frais à comptabiliser et lignes en proposition compris)."""
    company = _company(db, company_id)
    date_from, date_to = _periode(date_from, date_to, NON_RAPPROCHES_MAX_JOURS, "10 ans")
    comptes = _comptes(db, company.id, bank_id)
    workbook = Workbook()
    workbook.remove(workbook.active)
    pris: set[str] = set()
    nombres: dict[str, int] = {}
    for compte in comptes:
        operations = rapports_repository.operations_non_rapprochees(
            db, compte.id, date_from, date_to
        )
        ecritures = rapports_repository.ecritures_non_rapprochees(db, compte.id, date_from, date_to)
        if not operations and not ecritures:
            continue
        # Frais bancaires (règle de « À comptabiliser ») : signalés dans la colonne St.
        frais_ids = reconciliation_repository.fee_transaction_ids(db, [op.id for op in operations])
        nom = _nom_feuille(compte, pris)
        _feuille_compte(
            workbook.create_sheet(nom),
            compte,
            operations,
            ecritures,
            frais_ids,
            date_from,
            date_to,
            solde_comptable_service.solde_du_compte(db, compte, date_to),
        )
        nombres[nom] = len(operations) + len(ecritures)
    if not workbook.sheetnames:
        vide = workbook.create_sheet("État de rapprochement")
        vide.append(
            [
                f"Aucune ligne non rapprochée du {date_from:%d/%m/%Y} au {date_to:%d/%m/%Y}"
                f"{' pour ' + comptes[0].bank.code if bank_id is not None else ''}."
            ]
        )
    contenu = _octets(workbook)

    banque = comptes[0].bank.code if bank_id is not None else "toutes"
    _audit(
        db,
        rapport="non_rapproches",
        company_id=company.id,
        acteur_id=acteur_id,
        ip=ip,
        du=date_from,
        au=date_to,
        banque=banque,
        lignes=sum(nombres.values()),
    )
    nom = f"etat-rapprochement-{company.code}-{banque}-{date_from}-{date_to}.xlsx"
    return nom.lower(), contenu
