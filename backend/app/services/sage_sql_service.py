"""Grand livre des comptes bancaires lu directement dans la base Sage 100 (21/11/2026).

« Récupérer le GL » sur /ecritures : pour chaque compte courant MAD qui a un journal Sage et un
compte comptable (AWB, BMCE, BP, CIH aujourd'hui), les lignes de la période sont lues dans la base
Sage, mises dans un classeur aux colonnes du modèle Excel, puis passées au moteur d'import habituel
(`accounting_import_service`) : doublons, erreurs, écritures absentes, solde comptable après import.
Rien n'est enregistré sans confirmation, compte par compte. La confirmation relit la base : si la
copie de la nuit l'a changée depuis l'aperçu (empreinte différente), elle est refusée.
"""

import hashlib
import io
import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import BankAccount, Company
from app.repositories import accounting_repository, sage_sql_repository
from app.repositories.sage_sql_repository import COLONNES_GL, ConnexionSage
from app.services import account_service, accounting_import_service, position_service
from app.services.accounting_import_service import AccountingAnalysis, EntriesImport
from app.services.errors import ConflictError, NotFoundError

logger = logging.getLogger(__name__)

# Seuls les comptes courants en dirhams, pour le moment (décision du 21/11/2026)
TYPE_COMPTE = "Courant"
DEVISE = "MAD"

# Champ SIMTIS → colonne du classeur fabriqué (ordre de `COLONNES_GL`) : rien n'est deviné
MAPPING: dict[str, int | None] = {
    "date_ecriture": 0,
    "journal": 1,
    "compte": 2,
    "numero_piece": 3,
    "libelle": 4,
    "echeance": 5,
    "debit": 6,
    "credit": 7,
}

INJOIGNABLE = "Base Sage injoignable pour le moment : réessayez plus tard, ou importez le grand livre en Excel."
BASE_CHANGEE = (
    "La base Sage a été recopiée depuis la récupération : relancez « Récupérer le GL » avant de "
    "valider."
)


@dataclass
class CompteSage:
    account: BankAccount
    journaux: list[str]
    comptes: list[str]


@dataclass
class EtatSage:
    configure: bool
    base: str | None
    derniere_copie: datetime | None
    message: str | None
    comptes: list[CompteSage]


@dataclass
class AnalyseCompteSage:
    compte: CompteSage
    empreinte: str
    analyse: AccountingAnalysis
    # Solde du compte dans Sage à la date « Au » (écart avec le solde après import, 21/11/2026)
    solde_sage: "SoldeSage | None" = None


@dataclass
class AnalyseSage:
    du: date
    au: date
    derniere_copie: datetime | None
    comptes: list[AnalyseCompteSage]


def connexion() -> ConnexionSage:
    settings = get_settings()
    return ConnexionSage(
        host=settings.sage_sql_host,
        port=settings.sage_sql_port,
        database=settings.sage_sql_database,
        user=settings.sage_sql_user,
        password=settings.sage_sql_password,
    )


def societe(db: Session, company_id: int) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise NotFoundError("Société introuvable.")
    return company


def refus(company: Company) -> str | None:
    """Pourquoi la base Sage ne peut pas servir à cette société, ou None."""
    settings = get_settings()
    if not settings.sage_sql_configure:
        return "La récupération depuis la base Sage n'est pas configurée sur ce serveur."
    if company.code != settings.sage_sql_societe:
        return f"Pas de base Sage reliée à la société {company.nom}."
    return None


def comptes_concernes(db: Session, company_id: int) -> list[CompteSage]:
    """Comptes courants MAD actifs de la société qui ont un journal Sage et un compte comptable,
    dans l'ordre des banques."""
    comptes = []
    for account in accounting_repository.bank_journals(db, company_id):
        if account.type_compte != TYPE_COMPTE or account.devise != DEVISE:
            continue
        journaux = account_service.journaux_sage(account.journal_sage)
        prefixes = account_service.comptes_comptables(account.compte_comptable)
        if journaux and prefixes:
            comptes.append(CompteSage(account, journaux, prefixes))
    return sorted(comptes, key=lambda c: (c.account.bank.ordre_affichage, c.account.id))


def derniere_copie(cnx: ConnexionSage) -> datetime:
    try:
        return sage_sql_repository.derniere_copie(cnx)
    except Exception as error:  # pymssql : réseau, identifiants, base absente
        logger.warning("Base Sage injoignable : %s", error)
        raise ConflictError(INJOIGNABLE) from error


def etat(db: Session, company_id: int) -> EtatSage:
    """Connexion configurée, date de la dernière copie et comptes concernés (pour l'écran)."""
    company = societe(db, company_id)
    comptes = comptes_concernes(db, company.id)
    motif = refus(company)
    if motif:
        return EtatSage(False, None, None, motif, comptes)
    base = get_settings().sage_sql_database
    try:
        copie = derniere_copie(connexion())
    except ConflictError as error:
        return EtatSage(True, base, None, error.message, comptes)
    return EtatSage(True, base, copie, None, comptes)


def _verifier_periode(du: date, au: date) -> None:
    if du > au:
        raise ConflictError("La date de début doit précéder la date de fin.")


def lire(cnx: ConnexionSage, compte: CompteSage, du: date, au: date) -> list[tuple]:
    try:
        return sage_sql_repository.grand_livre(
            cnx, journaux=compte.journaux, comptes=compte.comptes, du=du, au=au
        )
    except Exception as error:
        logger.warning("Lecture du grand livre Sage impossible : %s", error)
        raise ConflictError(INJOIGNABLE) from error


CENTIME = Decimal("0.01")


@dataclass
class SoldeSage:
    """Solde d'un compte dans Sage au `jour` : du dernier à-nouveau (`debut`) au jour inclus,
    tous journaux (21/11/2026). Sage ne stocke aucun solde : il le recalcule de même."""

    debut: date | None
    solde: Decimal
    # (journal, débits, crédits, nombre de lignes) de la période, à-nouveaux compris
    totaux: list[tuple[str, Decimal, Decimal, int]]


def solde_sage(cnx: ConnexionSage, compte: CompteSage, jour: date) -> SoldeSage:
    try:
        debut = sage_sql_repository.debut_solde(cnx, comptes=compte.comptes, jour=jour)
        rows = (
            sage_sql_repository.totaux_par_journal(cnx, comptes=compte.comptes, du=debut, au=jour)
            if debut
            else []
        )
    except Exception as error:
        logger.warning("Solde Sage illisible : %s", error)
        raise ConflictError(INJOIGNABLE) from error
    totaux = [
        (str(journal).strip(), decimal(debit), decimal(credit), int(nb))
        for journal, debit, credit, nb in rows
    ]
    solde = sum((debit - credit for _, debit, credit, _ in totaux), Decimal("0.00"))
    return SoldeSage(debut, solde, totaux)


def decimal(valeur: object) -> Decimal:
    return Decimal(str(valeur or 0)).quantize(CENTIME)


def empreinte(lignes: list[tuple]) -> str:
    """Empreinte des lignes lues : la confirmation vérifie que la base n'a pas changé."""
    return hashlib.sha256(repr(lignes).encode("utf-8")).hexdigest()


def classeur(lignes: list[tuple]) -> bytes:
    """Lignes Sage → classeur .xlsx aux colonnes du modèle Excel, lu par le moteur d'import."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "GL Sage"
    sheet.append(COLONNES_GL)
    for ligne in lignes:
        sheet.append([value.strip() if isinstance(value, str) else value for value in ligne])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def nom_fichier(compte: CompteSage, du: date, au: date) -> str:
    """Nom de l'import dans l'historique, ex. « GL Sage AWB 5542-5242 du 01-11-2026 au … »."""
    return (
        f"GL Sage {compte.account.bank.code} {'-'.join(compte.journaux)} "
        f"du {du:%d-%m-%Y} au {au:%d-%m-%Y}.xlsx"
    )


def analyser(
    db: Session, company_id: int, du: date, au: date, today: date | None = None
) -> AnalyseSage:
    """Aperçu du grand livre de chaque compte concerné. Ne modifie pas la base SIMTIS."""
    company = societe(db, company_id)
    motif = refus(company)
    if motif:
        raise ConflictError(motif)
    _verifier_periode(du, au)
    comptes = comptes_concernes(db, company.id)
    if not comptes:
        raise ConflictError(
            "Aucun compte courant en dirhams n'a de journal Sage et de compte comptable "
            "(écran Comptes)."
        )
    cnx = connexion()
    copie = derniere_copie(cnx)
    today = today or position_service.business_today()
    resultats = []
    for compte in comptes:
        lignes = lire(cnx, compte, du, au)
        analyse = accounting_import_service.analyse_entries(
            db,
            company_id=company.id,
            fichier_nom=nom_fichier(compte, du, au),
            content=classeur(lignes),
            mapping=MAPPING,
            today=today,
        )
        resultats.append(
            AnalyseCompteSage(compte, empreinte(lignes), analyse, solde_sage(cnx, compte, au))
        )
    return AnalyseSage(du, au, copie, resultats)


def confirmer(
    db: Session,
    *,
    company_id: int,
    bank_account_id: int,
    du: date,
    au: date,
    empreinte_attendue: str,
    lignes_choisies: list[int],
    ecritures_supprimees: list[int],
    acteur_id: int,
    ip: str | None = None,
    today: date | None = None,
) -> EntriesImport:
    """Importe les lignes cochées d'un compte : la base Sage est relue et doit être inchangée."""
    company = societe(db, company_id)
    motif = refus(company)
    if motif:
        raise ConflictError(motif)
    _verifier_periode(du, au)
    compte = next(
        (c for c in comptes_concernes(db, company.id) if c.account.id == bank_account_id), None
    )
    if compte is None:
        raise NotFoundError("Compte introuvable parmi les comptes récupérés depuis Sage.")
    lignes = lire(connexion(), compte, du, au)
    if empreinte(lignes) != empreinte_attendue:
        raise ConflictError(BASE_CHANGEE)
    return accounting_import_service.confirm_entries(
        db,
        company_id=company.id,
        fichier_nom=nom_fichier(compte, du, au),
        content=classeur(lignes),
        mapping=MAPPING,
        feuille=None,
        garder_doublons=None,
        ecarter_erreurs=False,
        lignes_choisies=lignes_choisies,
        ecritures_supprimees=ecritures_supprimees,
        acteur_id=acteur_id,
        ip=ip,
        today=today,
        enregistrer_modele=False,
    )
