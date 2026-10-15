"""Rapports Excel (P16.4, 14/10/2026). Excel seulement (décision du 14/10/2026 : pas de PDF).

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
from sqlalchemy.orm import Session

from app.models import BankAccount
from app.repositories import account_repository, rapports_repository, reconciliation_repository
from app.services import audit_service, position_banques_service
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
