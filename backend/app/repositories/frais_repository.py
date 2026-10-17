"""Lectures de la comptabilisation des frais bancaires par SIMTIS : droits de timbre et
commissions (13/10/2026)."""

from datetime import date

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, aliased

from app.models import (
    AccountingEntry,
    BankTransaction,
    PointageType,
    ReconciliationMatch,
    ReconciliationMatchItem,
)
from app.repositories import reconciliation_repository

# Lectures larges en base ; les règles exactes sont dans `frais_service` (`type_timbre`,
# `type_commission`)
LIBELLE_TIMBRE_SQL = r"^\s*DROITS?\s+DE\s+TIMBRE"
LIBELLE_COMMISSION_SQL = r"^\s*(COMMISSION|TAXE\s+SUR\s+VALEUR\s+AJOUTEE|TVA\s+COM\s+EFFET)"
# Écriture Sage d'un jour : « DT D'ENREGISTREMENT » (apostrophe droite ou non), « COM »
ECRITURE_TIMBRE_SQL = r"^\s*DT\s+D.?\s*ENREGISTREMENT"
ECRITURE_COMMISSION_SQL = r"^\s*COM\s*$"
# Frais bancaires à TVA comprise (14/10/2026) : écriture Sage « FRAIS » du jour
# Les commissions à TVA comprise sont lues avec les autres commissions (écriture « COM »)
LIBELLE_FRAIS_SQL = r"^\s*FRAIS\W+R.CUP.R.S\W+PAR\W+LA\W+BANQUE"
ECRITURE_FRAIS_SQL = r"^\s*FRAIS\s*$"
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
            BankTransaction.libelle.op("~*")(libelle_sql),
            BankTransaction.id.not_in(actives),
        )
        .order_by(BankTransaction.date_operation, BankTransaction.id)
    )
    return list(db.scalars(query))


def jours_dans_sage(
    db: Session,
    company_id: int,
    account_ids: list[int],
    date_from: date,
    date_to: date,
    ecriture_sql: str,
) -> set[tuple[int, date]]:
    """(compte, jour) où Sage a déjà l'écriture du jour (« DT D'ENREGISTREMENT », « COM ») :
    jamais comptabilisé deux fois."""
    if not account_ids:
        return set()
    rows = db.execute(
        select(AccountingEntry.bank_account_id, AccountingEntry.date_ecriture).where(
            AccountingEntry.company_id == company_id,
            AccountingEntry.origine == "Sage",
            AccountingEntry.bank_account_id.in_(account_ids),
            AccountingEntry.date_ecriture.between(date_from, date_to),
            AccountingEntry.libelle.op("~*")(ecriture_sql),
        )
    )
    return {(row[0], row[1]) for row in rows}


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


def next_piece_number(db: Session, company_id: int, bank_id: int, annee: int, mois: int) -> int:
    """Numéro suivant du compteur (société, banque, mois), atomique : deux comptabilisations
    simultanées ne reçoivent jamais le même numéro (15/10/2026 ; par banque depuis le 16/10)."""
    statement = text(
        "INSERT INTO frais_piece_counters (company_id, bank_id, annee, mois, dernier) "
        "VALUES (:societe, :banque, :annee, :mois, 1) "
        "ON CONFLICT (company_id, bank_id, annee, mois) "
        "DO UPDATE SET dernier = frais_piece_counters.dernier + 1 RETURNING dernier"
    )
    return db.execute(
        statement, {"societe": company_id, "banque": bank_id, "annee": annee, "mois": mois}
    ).scalar_one()
