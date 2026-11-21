"""Écart entre le solde d'un compte dans Sage et son solde comptable SIMTIS (21/11/2026).

Solde Sage au jour J : lignes Sage des comptes comptables du compte, tous journaux, du dernier
à-nouveau (journal 9000) daté au plus tard J jusqu'à J (`sage_sql_service.solde_sage`). Solde
SIMTIS : celui de la carte « Solde comptable » (`solde_comptable_service`), inchangé.
Écart = Sage − SIMTIS, débiteur positif des deux côtés. Comptes courants MAD seulement.

Détail sur la même période : départ (à-nouveau Sage / solde SIMTIS de la veille), mouvements par
journal, écritures SIMTIS pas encore exportées vers Sage, lignes Sage passées hors des journaux
de banque du compte ; et, sur demande, la comparaison ligne à ligne des journaux de banque.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import BankAccount
from app.repositories import accounting_repository, sage_sql_repository
from app.repositories.sage_sql_repository import JOURNAL_A_NOUVEAUX
from app.services import (
    accounting_import_service,
    position_service,
    sage_sql_service,
    solde_comptable_service,
)
from app.services.accounting_import_service import EcritureAbsente, EntryLine
from app.services.errors import ConflictError, NotFoundError
from app.services.sage_sql_service import CompteSage

ZERO = Decimal("0.00")
LIMITE_HORS_JOURNAUX = 500


@dataclass
class SoldeSageCompte:
    compte: CompteSage
    jour: date
    debut: date | None  # date de l'à-nouveau dont part le solde Sage
    solde_sage: Decimal
    solde_simtis: Decimal | None  # None : solde d'ouverture SIMTIS à saisir
    ecart: Decimal | None  # Sage − SIMTIS


@dataclass
class EtatSoldesSage:
    configure: bool
    derniere_copie: datetime | None
    message: str | None
    comptes: list[SoldeSageCompte] = field(default_factory=list)


@dataclass
class LigneJournal:
    journal: str
    banque: bool  # journal Sage du compte (sinon : OD, autre banque...)
    sage: Decimal  # débits − crédits de la période
    simtis: Decimal
    ecart: Decimal
    nb_sage: int
    nb_simtis: int


@dataclass
class LigneSage:
    date_ecriture: date
    journal: str
    compte: str
    numero_piece: str | None
    libelle: str | None
    debit: Decimal
    credit: Decimal


@dataclass
class EcartDetail:
    solde: SoldeSageCompte
    # Début de la période côté SIMTIS : le lendemain de son ouverture si elle est plus récente
    debut_simtis: date | None
    depart_sage: Decimal
    depart_simtis: Decimal | None
    journaux: list[LigneJournal]
    non_exportees: Decimal  # débits − crédits des écritures SIMTIS pas encore dans Sage
    nb_non_exportees: int
    hors_journaux: list[LigneSage]
    hors_journaux_tronque: bool


@dataclass
class Comparaison:
    solde: SoldeSageCompte
    absentes_de_simtis: list[EntryLine]  # lignes Sage des journaux de banque pas dans SIMTIS
    absentes_de_sage: list[EcritureAbsente]  # écritures Sage de SIMTIS plus dans Sage


def _jour(jour: date | None) -> date:
    today = position_service.business_today()
    return min(jour or today, today)


def _solde(
    db: Session, compte: CompteSage, jour: date, sage: sage_sql_service.SoldeSage
) -> SoldeSageCompte:
    simtis = solde_comptable_service.solde_du_compte(db, compte.account, jour).solde
    ecart = None if simtis is None else sage.solde - simtis
    return SoldeSageCompte(compte, jour, sage.debut, sage.solde, simtis, ecart)


def soldes(db: Session, company_id: int, jour: date | None = None) -> EtatSoldesSage:
    """Solde Sage, solde SIMTIS et écart de chaque compte courant MAD de la société."""
    company = sage_sql_service.societe(db, company_id)
    refus = sage_sql_service.refus(company)
    if refus:
        return EtatSoldesSage(False, None, refus)
    jour = _jour(jour)
    cnx = sage_sql_service.connexion()
    try:
        copie = sage_sql_service.derniere_copie(cnx)
        comptes = [
            _solde(db, compte, jour, sage_sql_service.solde_sage(cnx, compte, jour))
            for compte in sage_sql_service.comptes_concernes(db, company.id)
        ]
    except ConflictError as error:
        return EtatSoldesSage(True, None, error.message)
    return EtatSoldesSage(True, copie, None, comptes)


def _compte(db: Session, bank_account_id: int) -> CompteSage:
    account = db.get(BankAccount, bank_account_id)
    if account is None:
        raise NotFoundError("Compte introuvable.")
    refus = sage_sql_service.refus(account.company)
    if refus:
        raise ConflictError(refus)
    compte = next(
        (
            c
            for c in sage_sql_service.comptes_concernes(db, account.company_id)
            if c.account.id == account.id
        ),
        None,
    )
    if compte is None:
        raise ConflictError(
            "Ce compte n'est pas comparé à Sage : seuls les comptes courants en dirhams qui ont un "
            "journal Sage et un compte comptable le sont."
        )
    return compte


def _ligne_sage(row: tuple) -> LigneSage:
    jour, journal, compte, piece, libelle, _echeance, debit, credit = row
    return LigneSage(
        date_ecriture=jour.date() if isinstance(jour, datetime) else jour,
        journal=str(journal).strip(),
        compte=str(compte).strip(),
        numero_piece=(piece or "").strip() or None,
        libelle=(libelle or "").strip() or None,
        debit=sage_sql_service.decimal(debit),
        credit=sage_sql_service.decimal(credit),
    )


def detail(db: Session, bank_account_id: int, jour: date | None = None) -> EcartDetail:
    """D'où vient l'écart d'un compte : départ, journaux, non exportées, lignes hors journaux."""
    compte = _compte(db, bank_account_id)
    jour = _jour(jour)
    cnx = sage_sql_service.connexion()
    sage = sage_sql_service.solde_sage(cnx, compte, jour)
    solde = _solde(db, compte, jour, sage)
    account = compte.account

    depart_sage = sum(
        (d - c for journal, d, c, _ in sage.totaux if journal == JOURNAL_A_NOUVEAUX), ZERO
    )
    par_journal: dict[str, list] = {}
    for journal, debit, credit, nb in sage.totaux:
        if journal != JOURNAL_A_NOUVEAUX:
            par_journal[journal] = [debit - credit, ZERO, nb, 0]

    debut_simtis, depart_simtis = None, None
    non_exportees, nb_non_exportees = ZERO, 0
    if sage.debut is not None:
        # Une ouverture SIMTIS plus récente que l'à-nouveau Sage : la période SIMTIS part d'elle
        debut_simtis = sage.debut
        if account.date_solde_comptable and account.date_solde_comptable >= sage.debut:
            debut_simtis = account.date_solde_comptable + timedelta(days=1)
        depart_simtis = solde_comptable_service.solde_du_compte(
            db, account, debut_simtis - timedelta(days=1)
        ).solde
        mouvements = accounting_repository.mouvements_par_journal(
            db, account.id, du=debut_simtis, au=jour
        )
        for journal, non_exportee, debit, credit, nb in mouvements:
            montant = debit - credit
            if non_exportee:
                non_exportees += montant
                nb_non_exportees += nb
                continue
            item = par_journal.setdefault(journal or "-", [ZERO, ZERO, 0, 0])
            item[1] += montant
            item[3] += nb

    ordre = {journal: index for index, journal in enumerate(compte.journaux)}
    journaux = [
        LigneJournal(journal, journal in ordre, sage_m, simtis_m, sage_m - simtis_m, nb_s, nb_t)
        for journal, (sage_m, simtis_m, nb_s, nb_t) in sorted(
            par_journal.items(), key=lambda item: (ordre.get(item[0], len(ordre)), item[0])
        )
    ]

    hors: list[tuple] = []
    if sage.debut is not None:
        try:
            hors = sage_sql_repository.lignes_hors_journaux(
                cnx,
                comptes=compte.comptes,
                journaux_exclus=[*compte.journaux, JOURNAL_A_NOUVEAUX],
                du=sage.debut,
                au=jour,
                limite=LIMITE_HORS_JOURNAUX + 1,
            )
        except Exception as error:
            raise ConflictError(sage_sql_service.INJOIGNABLE) from error
    return EcartDetail(
        solde=solde,
        debut_simtis=debut_simtis,
        depart_sage=depart_sage,
        depart_simtis=depart_simtis,
        journaux=journaux,
        non_exportees=non_exportees,
        nb_non_exportees=nb_non_exportees,
        hors_journaux=[_ligne_sage(row) for row in hors[:LIMITE_HORS_JOURNAUX]],
        hors_journaux_tronque=len(hors) > LIMITE_HORS_JOURNAUX,
    )


def comparer(db: Session, bank_account_id: int, jour: date | None = None) -> Comparaison:
    """Lignes à lignes, journaux de banque du compte, sur la période du solde Sage : lignes Sage
    absentes de SIMTIS, et écritures Sage de SIMTIS qui ne sont plus dans Sage."""
    compte = _compte(db, bank_account_id)
    jour = _jour(jour)
    cnx = sage_sql_service.connexion()
    sage = sage_sql_service.solde_sage(cnx, compte, jour)
    solde = _solde(db, compte, jour, sage)
    if sage.debut is None:
        return Comparaison(solde, [], [])
    lignes = sage_sql_service.lire(cnx, compte, sage.debut, jour)
    analyse = accounting_import_service.analyse_entries(
        db,
        company_id=compte.account.company_id,
        fichier_nom=sage_sql_service.nom_fichier(compte, sage.debut, jour),
        content=sage_sql_service.classeur(lignes),
        mapping=sage_sql_service.MAPPING,
    )
    # Tous les journaux de banque du compte, sur toute la période : un journal vidé dans Sage
    # compte aussi (l'import par fichier ne regarde que les journaux présents dans le fichier)
    absentes = accounting_import_service.ecritures_absentes_periode(
        db, compte.account, compte.journaux, sage.debut, jour, analyse.lignes
    )
    return Comparaison(
        solde, [line for line in analyse.lignes if line.statut != "Doublon"], absentes
    )
