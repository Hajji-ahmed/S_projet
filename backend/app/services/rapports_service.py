"""Rapports Excel (P16.4, 14/10/2026). Excel seulement (décision du 14/10/2026), sauf la position
bancaire, aussi en PDF depuis le 27/10/2026 (`position_pdf`, même tableau que l'Excel).

Aucun chiffre n'est recalculé ici :
- « Position du jour » reprend le tableau Banques tel que l'écran le calcule
  (`position_banques_service.banques_table`), dans sa structure : une colonne par banque, TOTAL,
  DEPASSEMENT ; la ligne LIGNE, une ligne « facilité de caisse » par jour, « Disponible Fc reel » ;
  un dernier solde connu repris d'un jour précédent est en italique gris, comme à l'écran ;
- « État de rapprochement » (refait le 30/10/2026) met côte à côte, compte par compte, les
  opérations du relevé et les écritures Sage de chaque rapprochement validé de la période, un bloc
  par code (au milieu : code, type, validé par / le), avec les totaux de chaque côté.
- « Lignes non rapprochées » (30/10/2026) met côte à côte, compte par compte, les opérations du
  relevé et les écritures Sage pas encore rapprochées de la période, comme l'écran Rapprochement.
Le lettrage et les écritures de frais pour Sage gardent leurs exports existants. Chaque export
est audité (`export_rapport`).
"""

from datetime import date, datetime
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

from app.models import AccountingEntry, BankAccount, BankTransaction, ReconciliationMatch
from app.repositories import account_repository, rapports_repository, reconciliation_repository
from app.services import audit_service, position_banques_service, solde_comptable_service
from app.services.account_service import fraction_to_pct
from app.services.errors import ConflictError, NotFoundError
from app.services.position_service import BUSINESS_TZ, LigneTableau, business_today
from app.services.reconciliation_service import montant_rapprochement
from app.services.solde_comptable_service import SoldeComptable

PERIODE_MAX_JOURS = 1827  # 5 ans, comme le lettrage
NON_RAPPROCHES_MAX_JOURS = 3653  # 10 ans pour « Lignes non rapprochées » (02/11/2026)
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


# --- Lignes non rapprochées (30/10/2026) ----------------------------------------------------------

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
        f"non rapprochées du {date_from:%d/%m/%Y} au {date_to:%d/%m/%Y}",
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
        ("Solde banque rectifié (solde du relevé + écritures non rapprochées)", banque),
        ("Solde compta rectifié (solde comptable + opérations non rapprochées)", compta),
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
        vide = workbook.create_sheet("Non rapprochées")
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
    return f"non-rapproches-{company.code}-{banque}-{date_from}-{date_to}.xlsx".lower(), contenu


# --- État de rapprochement (refait le 30/10/2026) -------------------------------------------------

BLOC_PAIR = PatternFill("solid", fgColor="F5F8FA")
SECTION = PatternFill("solid", fgColor="004F54")
SECTION_POLICE = Font(bold=True, color="FFFFFF")
SEPARATION = Side(style="thin", color="B7D7D9")
TOTAL_TRAIT = Border(top=Side(style="medium", color="004F54"))
COLONNES_OPERATIONS = (("Date", 10), ("Libellé", 46), ("Réf.", 14), ("Débit", 15),
                       ("Crédit", 15))  # fmt: skip
COLONNES_MILIEU = (("Code", 16), ("Type", 7), ("Validé par", 16), ("Validé le", 15))
COLONNES_ECRITURES = (("Date", 10), ("Libellé", 46), ("N° pièce", 14), ("Débit", 15),
                      ("Crédit", 15))  # fmt: skip
DEBUT_MILIEU = len(COLONNES_OPERATIONS) + 2
DEBUT_ECRITURES = DEBUT_MILIEU + len(COLONNES_MILIEU) + 1
PREMIERE_LIGNE = 5
FORMATS_COTE = ("DD/MM/YY", None, None, FORMAT_MONTANT, FORMAT_MONTANT)
ZERO = Decimal("0.00")


def _heure_locale(moment: datetime | None) -> datetime | None:
    """Excel ne connaît pas les fuseaux : l'heure du Maroc, sans fuseau."""
    return moment.astimezone(BUSINESS_TZ).replace(tzinfo=None) if moment else None


def debit_credit_sage(entry: AccountingEntry, devise: str) -> tuple[Decimal, Decimal]:
    """Débit et crédit de l'écriture dans la devise du compte, comme l'écran : le montant en devise
    d'un compte EUR / USD (une écriture Sage au débit y est négative), sinon le MAD."""
    if devise != "MAD" and entry.montant_devise is not None:
        montant = entry.montant_devise
        return (-montant if montant < 0 else ZERO), (montant if montant > 0 else ZERO)
    return entry.debit, entry.credit


Bloc = tuple[ReconciliationMatch, list[BankTransaction], list[AccountingEntry]]


def _en_tetes_rapprochement(sheet: Worksheet, unite: str) -> None:
    for debut, titre, colonnes in (
        (1, "Transactions bancaires", COLONNES_OPERATIONS),
        (DEBUT_MILIEU, "Rapprochement", COLONNES_MILIEU),
        (DEBUT_ECRITURES, "Écritures comptables", COLONNES_ECRITURES),
    ):
        fin = debut + len(colonnes) - 1
        for colonne in range(debut, fin + 1):
            sheet.cell(row=3, column=colonne).fill = SECTION
        sheet.merge_cells(start_row=3, start_column=debut, end_row=3, end_column=fin)
        cellule = sheet.cell(row=3, column=debut, value=titre)
        cellule.font = SECTION_POLICE
        cellule.alignment = Alignment(horizontal="center")
        for index, (nom, largeur) in enumerate(colonnes):
            montant = nom in ("Débit", "Crédit")
            cellule = sheet.cell(
                row=4, column=debut + index, value=f"{nom} ({unite})" if montant else nom
            )
            cellule.font = EN_TETE_ECRAN
            cellule.fill = EN_TETE
            cellule.alignment = Alignment(horizontal="right" if montant else "left")
            sheet.column_dimensions[get_column_letter(debut + index)].width = largeur
    for colonne in (DEBUT_MILIEU - 1, DEBUT_ECRITURES - 1):
        sheet.column_dimensions[get_column_letter(colonne)].width = 2
    sheet.freeze_panes = f"A{PREMIERE_LIGNE}"


def _feuille_rapprochements(
    sheet: Worksheet,
    compte: BankAccount,
    blocs: list[Bloc],
    noms: dict[int, str],
    date_from: date,
    date_to: date,
) -> None:
    """Un bloc de lignes par rapprochement : ses opérations à gauche, ses écritures à droite, ligne
    à ligne ; au milieu, sur la première ligne, le code, le type et la validation. Les blocs
    alternent blanc / gris clair et sont séparés par un trait fin."""
    sheet.sheet_view.showGridLines = False
    sheet.cell(
        row=1,
        column=1,
        value=f"{compte.company.nom} · {compte.bank.code} · {compte.devise} · {compte.numero} — "
        f"état de rapprochement du {date_from:%d/%m/%Y} au {date_to:%d/%m/%Y}",
    ).font = TITRE
    pluriel = "s" if len(blocs) > 1 else ""
    sheet.cell(
        row=2, column=1, value=f"{len(blocs)} rapprochement{pluriel} validé{pluriel}"
    ).font = Font(italic=True, color="71839B")
    _en_tetes_rapprochement(sheet, "DH" if compte.devise == "MAD" else compte.devise)

    zones = (
        range(1, DEBUT_MILIEU - 1),
        range(DEBUT_MILIEU, DEBUT_ECRITURES - 1),
        range(DEBUT_ECRITURES, DEBUT_ECRITURES + len(COLONNES_ECRITURES)),
    )
    totaux = [ZERO, ZERO, ZERO, ZERO]  # débit / crédit banque, débit / crédit Sage
    rang = PREMIERE_LIGNE
    for numero, (match, operations, ecritures) in enumerate(blocs):
        fond = BLOC_PAIR if numero % 2 else None
        hauteur = max(len(operations), len(ecritures), 1)
        for decalage in range(hauteur):
            ligne = rang + decalage
            # fond et trait sur toute la largeur du bloc, même là où un côté n'a plus de ligne
            for zone in zones:
                for colonne in zone:
                    case = sheet.cell(row=ligne, column=colonne)
                    case.alignment = Alignment(vertical="top")
                    if fond is not None:
                        case.fill = fond
                    if decalage == 0:
                        case.border = Border(top=SEPARATION)
            cotes = []
            if decalage < len(operations):
                op = operations[decalage]
                cotes.append((1, [op.date_operation, op.libelle, op.reference, op.debit or None,
                                  op.credit or None]))  # fmt: skip
                totaux[0] += op.debit
                totaux[1] += op.credit
            if decalage < len(ecritures):
                ec = ecritures[decalage]
                debit, credit = debit_credit_sage(ec, compte.devise)
                cotes.append((DEBUT_ECRITURES, [ec.date_ecriture, ec.libelle, ec.numero_piece,
                                                debit or None, credit or None]))  # fmt: skip
                totaux[2] += debit
                totaux[3] += credit
            for debut, valeurs in cotes:
                for index, valeur in enumerate(valeurs):
                    case = sheet.cell(row=ligne, column=debut + index, value=valeur)
                    if FORMATS_COTE[index]:
                        case.number_format = FORMATS_COTE[index]
        milieu = [match.code, match.type, noms.get(match.valide_par_id),
                  _heure_locale(match.valide_le)]  # fmt: skip
        for index, valeur in enumerate(milieu):
            sheet.cell(row=rang, column=DEBUT_MILIEU + index, value=valeur)
        sheet.cell(row=rang, column=DEBUT_MILIEU).font = Font(bold=True, color="004F54")
        sheet.cell(row=rang, column=DEBUT_MILIEU + 3).number_format = "DD/MM/YY HH:MM"
        rang += hauteur

    for debut, debit, credit in ((1, *totaux[:2]), (DEBUT_ECRITURES, *totaux[2:])):
        for colonne in range(debut, debut + len(COLONNES_OPERATIONS)):
            case = sheet.cell(row=rang, column=colonne)
            case.border = TOTAL_TRAIT
            case.fill = EN_TETE
            case.font = GRAS
        sheet.cell(row=rang, column=debut, value="Total")
        for decalage, valeur in ((3, debit), (4, credit)):
            sheet.cell(
                row=rang, column=debut + decalage, value=valeur
            ).number_format = FORMAT_MONTANT


def etat_rapprochement(
    db: Session,
    company_id: int,
    date_from: date | None,
    date_to: date | None,
    bank_id: int | None = None,
    *,
    acteur_id: int,
    ip: str | None,
) -> tuple[str, bytes]:
    """Rapprochements validés de la période (une de leurs opérations y est datée, comme le
    lettrage), une feuille par compte : opérations du relevé à gauche, écritures Sage à droite."""
    company = _company(db, company_id)
    date_from, date_to = _periode(date_from, date_to)
    comptes = _comptes(db, company.id, bank_id)
    retenus = {account.id for account in comptes}
    matches = reconciliation_repository.validated_matches(
        db,
        reconciliation_repository.decisions_query(
            company.id, bank_account_id=None, date_from=date_from, date_to=date_to
        ),
    )
    tx_ids = {i.bank_transaction_id for m in matches for i in m.items if i.bank_transaction_id}
    entry_ids = {i.accounting_entry_id for m in matches for i in m.items if i.accounting_entry_id}
    transactions = reconciliation_repository.transactions_with_bank(db, tx_ids)
    entries = reconciliation_repository.entries_with_bank(db, entry_ids)
    noms = reconciliation_repository.user_names(
        db, {m.valide_par_id for m in matches if m.valide_par_id}
    )

    blocs_par_compte: dict[int, list[Bloc]] = {}
    for match in matches:
        operations = sorted(
            (transactions[i.bank_transaction_id][0] for i in match.items if i.bank_transaction_id),
            key=lambda tx: (tx.date_operation, tx.id),
        )
        ecritures = sorted(
            (entries[i.accounting_entry_id][0] for i in match.items if i.accounting_entry_id),
            key=lambda ec: (ec.date_ecriture, ec.id),
        )
        # un rapprochement ne couvre qu'un compte : celui de ses opérations
        if operations and operations[0].bank_account_id in retenus:
            blocs_par_compte.setdefault(operations[0].bank_account_id, []).append(
                (match, operations, ecritures)
            )

    workbook = Workbook()
    workbook.remove(workbook.active)
    pris: set[str] = set()
    nombre = 0
    for compte in comptes:
        blocs = blocs_par_compte.get(compte.id)
        if not blocs:
            continue
        blocs.sort(key=lambda b: (b[1][0].date_operation, b[0].code or "", b[0].id))
        _feuille_rapprochements(
            workbook.create_sheet(_nom_feuille(compte, pris)),
            compte,
            blocs,
            noms,
            date_from,
            date_to,
        )
        nombre += len(blocs)
    if not workbook.sheetnames:
        vide = workbook.create_sheet("Rapprochées")
        vide.append(
            [
                f"Aucun rapprochement validé du {date_from:%d/%m/%Y} au {date_to:%d/%m/%Y}"
                f"{' pour ' + comptes[0].bank.code if bank_id is not None else ''}."
            ]
        )
    contenu = _octets(workbook)

    banque = comptes[0].bank.code if bank_id is not None else "toutes"
    _audit(
        db,
        rapport="etat_rapprochement",
        company_id=company.id,
        acteur_id=acteur_id,
        ip=ip,
        du=date_from,
        au=date_to,
        banque=banque,
        rapprochements=nombre,
    )
    nom = f"etat-rapprochement-{company.code}-{banque}-{date_from:%Y%m%d}-{date_to:%Y%m%d}.xlsx"
    return nom.lower(), contenu
