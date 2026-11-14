"""Lectures de la comptabilisation des frais bancaires par SIMTIS : droits de timbre et
commissions (13/10/2026)."""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.models import (
    AccountingEntry,
    BankTransaction,
    FraisJourEcarte,
    FraisLigne,
    PointageType,
    ReconciliationMatch,
    ReconciliationMatchItem,
)
from app.repositories import reconciliation_repository

# Lectures larges en base ; les règles exactes sont dans `frais_service` (`type_timbre`,
# `type_commission`)
# AWB (12/11/2026) : « TIMBRE/REM LCN REF … »
LIBELLE_TIMBRE_SQL = r"^\s*(DROITS?\s+DE\s+TIMBRE|FRAIS\s+(DE\s+)?TIMBRE|TIMBRE\W+REM\W+LCN)"
# Autres banques (09/11/2026) : TRANSFERT EMIS, COMMISSION…, TVA… SUR COMMISSION, COM FRAIS…
LIBELLE_COMMISSION_SQL = (
    r"^\s*(COMMISSION|TAXE\s+SUR\s+VALEUR\s+AJOUTEE|TVA\s|TRANSFERT\s+EMIS"
    # « COM & FRAIS / 3 LCN PAYEES » (AWB) : tout signe entre les deux mots (12/11/2026) ;
    # AWB : « COMM VIR EMIS / SRBM », « COM ABONNEMENT EBICS », commission carte « COM.ADOBE »
    r"|COM\W+FRAIS|COMM\s+VIR|COM\s+ABONNEMENT\s+EBICS|COM\.\S"
    # BP (14/11/2026) : « ABONNEMENT BP E-CORPORATE », TVA sur une ligne à part
    r"|ABONNEMENT\W+BP\W+E\W*CORPORATE)"
)
# Écriture Sage d'un jour : « DT D'ENREGISTREMENT » (apostrophe droite ou non), « COM »
ECRITURE_TIMBRE_SQL = r"^\s*DT\s+D.?\s*ENREGISTREMENT"
ECRITURE_COMMISSION_SQL = r"^\s*COM\s*$"
# Frais bancaires à TVA comprise (14/10/2026) : écriture Sage « FRAIS » du jour
# Les commissions à TVA comprise sont lues avec les autres commissions (écriture « COM »)
LIBELLE_FRAIS_SQL = (
    r"^\s*(FRAIS\W+(R.CUP.R.S\W+PAR\W+LA\W+BANQUE|SWIFT\W+CREDOC|ENCAISSEMENT\W+DE\W+CH"
    # CIH (11/11/2026)
    r"|CAUTION\W+NUM.RO|PDL\W+CREDOC"
    # AWB (12/11/2026)
    r"|ATTIJARI\W+NET\W+ENTREPRISE|MODULE\W+DOCNET|POUR\W+CERTIFICATION\W+CH|OPERATION\W+N\W"
    r"|RELEVE\W+CAUTION)"
    # CIH (12/11/2026) : la banque est vérifiée par `frais_service.type_frais_tva`
    r"|AGIOS\W+ESCOMPTE\W+LCN)"
)
ECRITURE_FRAIS_SQL = r"^\s*FRAIS\s*$"
# Intérêts d'escompte LCN de BP et leur TVA sur une ligne à part (14/11/2026) : écriture
# « FRAIS D'ESCOMPTE ». La TVA est rattachée à son intérêt par `frais_service.associer_tva`
LIBELLE_ESCOMPTE_SQL = (
    r"^\s*(INTERET\W+REMISE\W+LCN\W+A\W+L\W*ESCOMPTE|TAXE\s+SUR\s+VALEUR\s+AJOUTEE|TVA\s)"
)
# Écriture Sage « FRAIS D'ESCOMPTE », seule ou suivie du n° de remise (« FRAIS D'ESCOMPTE/7122271 »
# en production)
ECRITURE_ESCOMPTE_SQL = r"^\s*FRAIS\s+D\W?\s*ESCOMPTE\s*($|/)"
# Opérations qu'une TVA sur une ligne à part peut suivre, et ces TVA : commissions, abonnement,
# intérêts d'escompte (14/11/2026)
LIBELLE_TVA_SQL = f"{LIBELLE_COMMISSION_SQL}|{LIBELLE_ESCOMPTE_SQL}"
STATUTS_LIBRES = ("Non rapprochée", "À vérifier")


def frais_libres(
    db: Session, account_ids: list[int], date_from: date, date_to: date, libelle_sql: str
) -> list[BankTransaction]:
    """Frais débités dont le libellé répond à `libelle_sql`, ni rapprochés ni dans une
    correspondance active."""
    if not account_ids:
        return []
    actives = select(ReconciliationMatchItem.bank_transaction_id).where(
        ReconciliationMatchItem.actif.is_(True),
        ReconciliationMatchItem.bank_transaction_id.is_not(None),
    )
    query = (
        select(BankTransaction)
        .where(
            BankTransaction.bank_account_id.in_(account_ids),
            BankTransaction.date_operation.between(date_from, date_to),
            BankTransaction.montant < 0,
            BankTransaction.statut.in_(STATUTS_LIBRES),
            BankTransaction.en_cours.is_(False),
            BankTransaction.libelle.op("~*")(libelle_sql),
            BankTransaction.id.not_in(actives),
        )
        .order_by(BankTransaction.date_operation, BankTransaction.id)
    )
    return list(db.scalars(query))


def montants_dans_sage(
    db: Session,
    company_id: int,
    account_ids: list[int],
    date_from: date,
    date_to: date,
    ecriture_sql: str,
) -> dict[tuple[int, date], list[Decimal]]:
    """Montants (positifs) des écritures Sage de la famille (« DT D'ENREGISTREMENT », « COM »,
    « FRAIS »), par (compte, jour) : un frais du même montant, ou une journée dont les frais font
    ce total, est déjà passé dans Sage (13/11/2026, une écriture par frais)."""
    if not account_ids:
        return {}
    rows = db.execute(
        select(
            AccountingEntry.bank_account_id, AccountingEntry.date_ecriture, AccountingEntry.montant
        )
        .where(
            AccountingEntry.company_id == company_id,
            AccountingEntry.origine != "SIMTIS",
            AccountingEntry.bank_account_id.in_(account_ids),
            AccountingEntry.date_ecriture.between(date_from, date_to),
            AccountingEntry.libelle.op("~*")(ecriture_sql),
        )
        .order_by(AccountingEntry.id)
    )
    montants: dict[tuple[int, date], list[Decimal]] = {}
    for account_id, jour, montant in rows:
        montants.setdefault((account_id, jour), []).append(abs(montant))
    return montants


def ecritures_simtis(
    db: Session,
    company_id: int,
    *,
    bank_account_id: int | None,
    date_from: date | None,
    date_to: date | None,
    non_exportees: bool = False,
    libelle: str | None = None,
) -> list[tuple[AccountingEntry, str | None, int]]:
    """Écritures préparées par SIMTIS : (écriture, code du rapprochement, nombre d'opérations),
    de la plus récente à la plus ancienne."""
    nb = (
        select(func.count())
        .select_from(ReconciliationMatchItem)
        .where(
            ReconciliationMatchItem.match_id == ReconciliationMatch.id,
            ReconciliationMatchItem.actif.is_(True),
            ReconciliationMatchItem.bank_transaction_id.is_not(None),
        )
        .correlate(ReconciliationMatch)
        .scalar_subquery()
    )
    query = (
        select(AccountingEntry, ReconciliationMatch.code, nb)
        .outerjoin(
            ReconciliationMatchItem,
            (ReconciliationMatchItem.accounting_entry_id == AccountingEntry.id)
            & ReconciliationMatchItem.actif.is_(True),
        )
        .outerjoin(ReconciliationMatch, ReconciliationMatch.id == ReconciliationMatchItem.match_id)
        .where(AccountingEntry.company_id == company_id, AccountingEntry.origine == "SIMTIS")
        .order_by(AccountingEntry.date_ecriture.desc(), AccountingEntry.id.desc())
    )
    if bank_account_id is not None:
        query = query.where(AccountingEntry.bank_account_id == bank_account_id)
    if date_from is not None:
        query = query.where(AccountingEntry.date_ecriture >= date_from)
    if date_to is not None:
        query = query.where(AccountingEntry.date_ecriture <= date_to)
    if non_exportees:
        query = query.where(AccountingEntry.exportee_le.is_(None))
    if libelle is not None:
        query = query.where(AccountingEntry.libelle == libelle)
    return [(row[0], row[1], row[2] or 0) for row in db.execute(query)]


def active_match_of_entry(db: Session, entry_id: int) -> ReconciliationMatch | None:
    return db.scalar(
        select(ReconciliationMatch)
        .join(ReconciliationMatchItem, ReconciliationMatchItem.match_id == ReconciliationMatch.id)
        .where(
            ReconciliationMatchItem.accounting_entry_id == entry_id,
            ReconciliationMatchItem.actif.is_(True),
        )
    )


def simtis_entries_like(
    db: Session, company_id: int, keys: set[tuple[int, date]]
) -> list[AccountingEntry]:
    """Écritures SIMTIS des (compte, jour) demandés : pour reconnaître leur retour dans un export
    Sage."""
    if not keys:
        return []
    account_ids = {key[0] for key in keys}
    dates = {key[1] for key in keys}
    rows = db.scalars(
        select(AccountingEntry).where(
            AccountingEntry.company_id == company_id,
            AccountingEntry.origine == "SIMTIS",
            AccountingEntry.bank_account_id.in_(account_ids),
            AccountingEntry.date_ecriture.in_(dates),
        )
    )
    return [row for row in rows if (row.bank_account_id, row.date_ecriture) in keys]


def pieces_simtis_exportees(db: Session, company_id: int, pieces: set[str]) -> set[str]:
    """Parmi `pieces` (en majuscules), les N° pièce d'écritures SIMTIS déjà exportées vers Sage :
    pour repérer un tableau des frais importé deux fois dans Sage (10/11/2026)."""
    if not pieces:
        return set()
    numero = func.upper(AccountingEntry.numero_piece)
    return set(
        db.scalars(
            select(numero).where(
                AccountingEntry.company_id == company_id,
                AccountingEntry.origine == "SIMTIS",
                AccountingEntry.exportee_le.is_not(None),
                numero.in_(pieces),
            )
        )
    )


def operations_of_entries(db: Session, entry_ids: list[int]) -> dict[int, list[BankTransaction]]:
    """Opérations rapprochées (correspondance active) de chaque écriture demandée."""
    if not entry_ids:
        return {}
    entry_item = aliased(ReconciliationMatchItem)
    rows = db.execute(
        select(entry_item.accounting_entry_id, BankTransaction)
        .join(ReconciliationMatchItem, ReconciliationMatchItem.match_id == entry_item.match_id)
        .join(BankTransaction, BankTransaction.id == ReconciliationMatchItem.bank_transaction_id)
        .where(
            entry_item.accounting_entry_id.in_(entry_ids),
            entry_item.actif.is_(True),
            ReconciliationMatchItem.actif.is_(True),
        )
        .order_by(BankTransaction.id)
    )
    result: dict[int, list[BankTransaction]] = {}
    for entry_id, tx in rows:
        result.setdefault(entry_id, []).append(tx)
    return result


def _libres_a_comptabiliser():
    """Frais « Non rapprochée » (vue « À comptabiliser ») sans correspondance active."""
    actives = select(ReconciliationMatchItem.bank_transaction_id).where(
        ReconciliationMatchItem.actif.is_(True),
        ReconciliationMatchItem.bank_transaction_id.is_not(None),
    )
    return (
        BankTransaction.statut == "Non rapprochée",
        reconciliation_repository.frais_bancaire(),
        BankTransaction.id.not_in(actives),
        # Opération en cours (20/10/2026) : ni comptabilisée, ni rapprochée
        BankTransaction.en_cours.is_(False),
    )


def autres_frais(
    db: Session, account_ids: list[int], date_from: date, date_to: date
) -> list[tuple[BankTransaction, str | None]]:
    """Frais encore à comptabiliser (opération, libellé de son pointage), du plus récent au plus
    ancien : SIMTIS retire ensuite ceux qu'il comptabilise en automatique."""
    if not account_ids:
        return []
    rows = db.execute(
        select(BankTransaction, PointageType.libelle)
        .outerjoin(PointageType, PointageType.id == BankTransaction.pointage_type_id)
        .where(
            BankTransaction.bank_account_id.in_(account_ids),
            BankTransaction.date_operation.between(date_from, date_to),
            *_libres_a_comptabiliser(),
        )
        .order_by(BankTransaction.date_operation.desc(), BankTransaction.id.desc())
    )
    return [(row[0], row[1]) for row in rows]


def frais_libres_par_ids(
    db: Session, account_ids: list[int], ids: list[int]
) -> list[BankTransaction]:
    """Parmi `ids`, les frais encore à comptabiliser des comptes donnés."""
    if not account_ids or not ids:
        return []
    return list(
        db.scalars(
            select(BankTransaction)
            .where(
                BankTransaction.id.in_(ids),
                BankTransaction.bank_account_id.in_(account_ids),
                *_libres_a_comptabiliser(),
            )
            .order_by(BankTransaction.date_operation, BankTransaction.id)
        )
    )


# --- Propositions modifiées ou écartées (19/10/2026) ---------------------------------------------


def lignes_saisies(db: Session, entry_ids: list[int]) -> dict[int, list[FraisLigne]]:
    """Lignes saisies de chaque écriture demandée, dans leur ordre ; absente = lignes calculées."""
    if not entry_ids:
        return {}
    result: dict[int, list[FraisLigne]] = {}
    for ligne in db.scalars(
        select(FraisLigne)
        .where(FraisLigne.accounting_entry_id.in_(entry_ids))
        .order_by(FraisLigne.accounting_entry_id, FraisLigne.ordre)
    ):
        result.setdefault(ligne.accounting_entry_id, []).append(ligne)
    return result


def jours_ecartes(
    db: Session, account_ids: list[int], date_from: date, date_to: date
) -> list[tuple[FraisJourEcarte, BankTransaction | None]]:
    """Journées et opérations écartées des comptes sur la période, de la plus récente à la plus
    ancienne, avec l'opération écartée (None pour une journée entière)."""
    if not account_ids:
        return []
    rows = db.execute(
        select(FraisJourEcarte, BankTransaction)
        .outerjoin(BankTransaction, BankTransaction.id == FraisJourEcarte.bank_transaction_id)
        .where(
            FraisJourEcarte.bank_account_id.in_(account_ids),
            FraisJourEcarte.jour.between(date_from, date_to),
        )
        .order_by(FraisJourEcarte.jour.desc(), FraisJourEcarte.id.desc())
    )
    return [(ecarte, tx) for ecarte, tx in rows]


def jour_ecarte(
    db: Session, bank_account_id: int, jour: date, famille: str, transaction_id: int | None = None
) -> FraisJourEcarte | None:
    """Écartement d'une journée (sans opération) ou d'une opération (13/11/2026)."""
    operation = (
        FraisJourEcarte.bank_transaction_id.is_(None)
        if transaction_id is None
        else FraisJourEcarte.bank_transaction_id == transaction_id
    )
    return db.scalar(
        select(FraisJourEcarte).where(
            FraisJourEcarte.bank_account_id == bank_account_id,
            FraisJourEcarte.jour == jour,
            FraisJourEcarte.famille == famille,
            operation,
        )
    )


def frais_au_dessus(
    db: Session, account_ids: list[int], date_from: date, date_to: date, seuil
) -> list[tuple[BankTransaction, str | None, str | None]]:
    """Frais débités de plus de `seuil` (règle de « À comptabiliser »), quel que soit leur
    statut, avec le N° pièce et l'origine de l'écriture de leur rapprochement actif (19/10/2026)."""
    if not account_ids:
        return []
    item_tx = aliased(ReconciliationMatchItem)
    item_ec = aliased(ReconciliationMatchItem)
    rows = db.execute(
        select(BankTransaction, AccountingEntry.numero_piece, AccountingEntry.origine)
        .outerjoin(
            item_tx,
            (item_tx.bank_transaction_id == BankTransaction.id) & item_tx.actif.is_(True),
        )
        .outerjoin(
            item_ec,
            (item_ec.match_id == item_tx.match_id)
            & item_ec.actif.is_(True)
            & item_ec.accounting_entry_id.is_not(None),
        )
        .outerjoin(AccountingEntry, AccountingEntry.id == item_ec.accounting_entry_id)
        .where(
            BankTransaction.bank_account_id.in_(account_ids),
            BankTransaction.date_operation.between(date_from, date_to),
            BankTransaction.montant < -seuil,
            reconciliation_repository.frais_bancaire(),
        )
        .order_by(BankTransaction.date_operation, BankTransaction.id)
    )
    vus: set[int] = set()
    result = []
    for tx, piece, origine in rows:
        if tx.id in vus:
            continue
        vus.add(tx.id)
        result.append((tx, piece, origine))
    return result
