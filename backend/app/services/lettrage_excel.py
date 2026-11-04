"""Classeur du lettrage (refait le 04/11/2026) : une feuille par compte, chaque rapprochement validé
en un bloc de lignes, les opérations du relevé à gauche et les écritures comptables à droite, une
flèche « ⇄ » entre les deux. Dans un bloc, une opération est mise en face de l'écriture de même
montant (sens opposé) ; le reste est placé en face dans l'ordre des dates.

Les montants comparés sont ceux du rapprochement (`montant_rapprochement`) : le montant en devise
d'une écriture d'un compte EUR / USD, que le classeur écrit aussi dans la devise du compte."""

from collections import defaultdict, deque
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from itertools import zip_longest
from typing import TypeVar

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from app.models import AccountingEntry, BankAccount, BankTransaction, ReconciliationMatch
from app.services.position_service import BUSINESS_TZ

Op = TypeVar("Op")
Ec = TypeVar("Ec")

ZERO = Decimal("0.00")
FLECHE = "⇄"
FORMAT_MONTANT = "#,##0.00"
TITRE = Font(bold=True, size=13, color="004F54")
SOUS_TITRE = Font(italic=True, color="71839B")
SECTION = PatternFill("solid", fgColor="004F54")
SECTION_POLICE = Font(bold=True, color="FFFFFF")
EN_TETE = PatternFill("solid", fgColor="E7F6F4")
EN_TETE_POLICE = Font(bold=True, color="004F54")
BLOC_PAIR = PatternFill("solid", fgColor="F5F8FA")
SEPARATION = Side(style="thin", color="B7D7D9")
TOTAL_TRAIT = Border(top=Side(style="medium", color="004F54"))
CODE_POLICE = Font(bold=True, color="004F54")
FLECHE_POLICE = Font(bold=True, color="18B7C8")
GRAS = Font(bold=True)

# (titre de la bande, première colonne, colonnes (nom, largeur))
RAPPROCHEMENT = ("Rapprochement", 1, (("Code", 16), ("Validé le", 15)))
BANQUE = ("Banque", 3, (("Date", 10), ("Libellé", 46), ("Réf.", 14), ("Débit", 15),
                        ("Crédit", 15)))  # fmt: skip
COLONNE_FLECHE = 8
COMPTABILITE = ("Comptabilité", 9, (("Date", 10), ("N° pièce", 14), ("Libellé", 46),
                                    ("Débit", 15), ("Crédit", 15)))  # fmt: skip
DERNIERE_COLONNE = 13
PREMIERE_LIGNE = 5


def en_face(
    operations: list[Op],
    ecritures: list[Ec],
    cle_operation: Callable[[Op], Hashable],
    cle_ecriture: Callable[[Ec], Hashable],
    date_operation: Callable[[Op], date],
    date_ecriture: Callable[[Ec], date],
) -> list[tuple[Op | None, Ec | None]]:
    """Lignes d'un bloc : chaque opération face à la première écriture libre de même clé (montant
    opposé), puis les restes face à face dans l'ordre des dates ; un côté plus long laisse des
    cases vides. Lignes triées par date (celle de l'opération, sinon de l'écriture)."""
    operations = sorted(operations, key=date_operation)
    libres: dict[Hashable, deque[Ec]] = defaultdict(deque)
    for ecriture in sorted(ecritures, key=date_ecriture):
        libres[cle_ecriture(ecriture)].append(ecriture)
    lignes: list[tuple[Op | None, Ec | None]] = []
    seules: list[Op] = []
    for operation in operations:
        file = libres.get(cle_operation(operation))
        if file:
            lignes.append((operation, file.popleft()))
        else:
            seules.append(operation)
    restes = sorted((e for file in libres.values() for e in file), key=date_ecriture)
    lignes.extend(zip_longest(seules, restes))

    def cle(ligne: tuple[Op | None, Ec | None]) -> date:
        operation, ecriture = ligne
        return date_operation(operation) if operation is not None else date_ecriture(ecriture)

    return sorted(lignes, key=cle)


def montant_rapprochement(entry: AccountingEntry) -> Decimal:
    """Même règle que `reconciliation_service.montant_rapprochement` (sans l'importer : ce service
    importe ce module)."""
    return entry.montant_devise if entry.montant_devise is not None else entry.montant


def debit_credit(entry: AccountingEntry, devise: str) -> tuple[Decimal, Decimal]:
    """Débit et crédit de l'écriture dans la devise du compte (une écriture au débit est négative
    en devise), sinon en MAD."""
    if devise != "MAD" and entry.montant_devise is not None:
        montant = entry.montant_devise
        return (-montant if montant < 0 else ZERO), (montant if montant > 0 else ZERO)
    return entry.debit, entry.credit


def _heure_locale(moment: datetime | None) -> datetime | None:
    """Excel ne connaît pas les fuseaux : l'heure du Maroc, sans fuseau."""
    return moment.astimezone(BUSINESS_TZ).replace(tzinfo=None) if moment else None


@dataclass
class Bloc:
    match: ReconciliationMatch
    lignes: list[tuple[BankTransaction | None, AccountingEntry | None]]


def bloc(
    match: ReconciliationMatch,
    operations: list[BankTransaction],
    ecritures: list[AccountingEntry],
) -> Bloc:
    # Ordre stable à date égale : celui de l'import
    operations = sorted(operations, key=lambda tx: (tx.date_operation, tx.id))
    ecritures = sorted(ecritures, key=lambda ec: (ec.date_ecriture, ec.id))
    return Bloc(
        match,
        en_face(
            operations,
            ecritures,
            lambda tx: tx.montant,
            lambda ec: -montant_rapprochement(ec),
            lambda tx: tx.date_operation,
            lambda ec: ec.date_ecriture,
        ),
    )


def _periode(date_from: date | None, date_to: date | None) -> str:
    debut = f"du {date_from:%d/%m/%Y}" if date_from else "depuis le début"
    fin = f"au {date_to:%d/%m/%Y}" if date_to else "à aujourd'hui"
    return f"{debut} {fin}"


def _en_tetes(sheet: Worksheet, unite: str) -> None:
    for titre, debut, colonnes in (RAPPROCHEMENT, BANQUE, COMPTABILITE):
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
            cellule.font = EN_TETE_POLICE
            cellule.fill = EN_TETE
            cellule.alignment = Alignment(horizontal="right" if montant else "left")
            sheet.column_dimensions[get_column_letter(debut + index)].width = largeur
    for ligne in (3, 4):
        sheet.cell(row=ligne, column=COLONNE_FLECHE).fill = SECTION if ligne == 3 else EN_TETE
    sheet.column_dimensions[get_column_letter(COLONNE_FLECHE)].width = 4
    sheet.freeze_panes = f"A{PREMIERE_LIGNE}"


def _ecrire(sheet: Worksheet, ligne: int, debut: int, valeurs: list) -> None:
    for index, valeur in enumerate(valeurs):
        case = sheet.cell(row=ligne, column=debut + index, value=valeur)
        if isinstance(valeur, date):
            case.number_format = "DD/MM/YY"
        elif isinstance(valeur, Decimal):
            case.number_format = FORMAT_MONTANT


def feuille(
    sheet: Worksheet,
    compte: BankAccount,
    blocs: list[Bloc],
    date_from: date | None,
    date_to: date | None,
) -> None:
    """Un bloc de lignes par rapprochement ; les blocs alternent blanc / gris clair, séparés par
    un trait fin ; le code et la date de validation sur la première ligne ; totaux en bas."""
    sheet.sheet_view.showGridLines = False
    sheet.cell(
        row=1,
        column=1,
        value=f"{compte.company.nom} · {compte.bank.code} · {compte.devise} · {compte.numero} — "
        f"lettrage {_periode(date_from, date_to)}",
    ).font = TITRE
    pluriel = "s" if len(blocs) > 1 else ""
    sheet.cell(
        row=2, column=1, value=f"{len(blocs)} rapprochement{pluriel} validé{pluriel}"
    ).font = SOUS_TITRE
    _en_tetes(sheet, "DH" if compte.devise == "MAD" else compte.devise)

    totaux = [ZERO, ZERO, ZERO, ZERO]  # débit / crédit banque, débit / crédit comptabilité
    rang = PREMIERE_LIGNE
    for numero, element in enumerate(blocs):
        fond = BLOC_PAIR if numero % 2 else None
        for decalage, (operation, ecriture) in enumerate(element.lignes):
            ligne = rang + decalage
            for colonne in range(1, DERNIERE_COLONNE + 1):
                case = sheet.cell(row=ligne, column=colonne)
                case.alignment = Alignment(vertical="top")
                if fond is not None:
                    case.fill = fond
                if decalage == 0:
                    case.border = Border(top=SEPARATION)
            if operation is not None:
                _ecrire(sheet, ligne, BANQUE[1], [operation.date_operation, operation.libelle,
                        operation.reference, operation.debit or None,
                        operation.credit or None])  # fmt: skip
                totaux[0] += operation.debit
                totaux[1] += operation.credit
            if ecriture is not None:
                debit, credit = debit_credit(ecriture, compte.devise)
                _ecrire(sheet, ligne, COMPTABILITE[1], [ecriture.date_ecriture,
                        ecriture.numero_piece, ecriture.libelle, debit or None,
                        credit or None])  # fmt: skip
                totaux[2] += debit
                totaux[3] += credit
            if operation is not None and ecriture is not None:
                fleche = sheet.cell(row=ligne, column=COLONNE_FLECHE, value=FLECHE)
                fleche.font = FLECHE_POLICE
                fleche.alignment = Alignment(horizontal="center", vertical="top")
        sheet.cell(row=rang, column=1, value=element.match.code).font = CODE_POLICE
        sheet.cell(
            row=rang, column=2, value=_heure_locale(element.match.valide_le)
        ).number_format = "DD/MM/YY HH:MM"
        rang += max(len(element.lignes), 1)

    for colonne in range(1, DERNIERE_COLONNE + 1):
        case = sheet.cell(row=rang, column=colonne)
        case.border = TOTAL_TRAIT
        case.fill = EN_TETE
        case.font = GRAS
    sheet.cell(row=rang, column=1, value="Total")
    for colonne, valeur in zip((6, 7, 12, 13), totaux, strict=True):
        sheet.cell(row=rang, column=colonne, value=valeur).number_format = FORMAT_MONTANT


def nom_feuille(compte: BankAccount, pris: set[str]) -> str:
    base = f"{compte.bank.code} {compte.devise} {compte.numero[-4:]}"
    nom, suite = base[:31], 2
    while nom in pris:
        nom, suite = f"{base[:27]} {suite}", suite + 1
    pris.add(nom)
    return nom


def classeur(
    par_compte: list[tuple[BankAccount, list[Bloc]]],
    date_from: date | None,
    date_to: date | None,
) -> bytes:
    """Une feuille par compte qui a au moins un rapprochement ; sans rapprochement, une feuille
    « Lettrage » qui le dit."""
    workbook = Workbook()
    workbook.remove(workbook.active)
    pris: set[str] = set()
    for compte, blocs in par_compte:
        feuille(workbook.create_sheet(nom_feuille(compte, pris)), compte, blocs, date_from, date_to)
    if not workbook.sheetnames:
        workbook.create_sheet("Lettrage").append(
            [f"Aucun rapprochement validé {_periode(date_from, date_to)}."]
        )
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
