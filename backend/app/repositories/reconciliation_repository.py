"""Lectures et écritures du rapprochement 1→1 (P11)."""

from datetime import date
from decimal import Decimal

from sqlalchemy import Select, and_, delete, func, or_, select, text, update
from sqlalchemy.orm import Session, aliased, selectinload

from app.models import (
    AccountingEntry,
    Bank,
    BankAccount,
    BankTransaction,
    Company,
    PointageType,
    ReconciliationMatch,
    ReconciliationMatchItem,
    ReconciliationRule,
    User,
)
from app.services.reconciliation_scoring import AUTRE, TYPES_BANQUE, TYPES_SAGE, regex_type

# Statuts d'une correspondance qui retiennent ses éléments
STATUTS_ACTIFS = ("Proposée", "Validée")
# Lignes qu'un nouveau passage du moteur ne touche jamais
STATUTS_FIGES = ("Rapprochée", "Écart")


def lock_company(db: Session, company_id: int, *, nowait: bool = False) -> Company | None:
    """Verrouille la société : deux rapprochements de la même société ne s'exécutent jamais en même
    temps (lancement, validation, rapprochement manuel). Avec `nowait`, une société déjà
    verrouillée lève aussitôt `OperationalError` au lieu d'attendre (15/10/2026)."""
    return db.scalar(select(Company).where(Company.id == company_id).with_for_update(nowait=nowait))


def all_rules(db: Session) -> list[ReconciliationRule]:
    """Toutes les règles, actives ou non : un critère désactivé vaut 0 point."""
    return list(db.scalars(select(ReconciliationRule)))


def company_accounts(
    db: Session, company_id: int, bank_account_id: int | None = None
) -> list[BankAccount]:
    """Comptes de la société (actifs ou non : un compte fermé garde ses opérations à rapprocher)."""
    query = select(BankAccount).where(BankAccount.company_id == company_id)
    if bank_account_id is not None:
        query = query.where(BankAccount.id == bank_account_id)
    return list(db.scalars(query))


def _active_transaction_ids() -> Select:
    return select(ReconciliationMatchItem.bank_transaction_id).where(
        ReconciliationMatchItem.actif.is_(True),
        ReconciliationMatchItem.bank_transaction_id.is_not(None),
    )


def _active_entry_ids() -> Select:
    return select(ReconciliationMatchItem.accounting_entry_id).where(
        ReconciliationMatchItem.actif.is_(True),
        ReconciliationMatchItem.accounting_entry_id.is_not(None),
    )


def free_transactions(
    db: Session, account_ids: list[int], date_from: date, date_to: date
) -> list[BankTransaction]:
    """Opérations de la période qui ne font partie d'aucune correspondance active."""
    query = (
        select(BankTransaction)
        .where(
            BankTransaction.bank_account_id.in_(account_ids),
            BankTransaction.date_operation >= date_from,
            BankTransaction.date_operation <= date_to,
            BankTransaction.statut.not_in(STATUTS_FIGES),
            BankTransaction.id.not_in(_active_transaction_ids()),
        )
        .order_by(BankTransaction.date_operation, BankTransaction.id)
    )
    return list(db.scalars(query))


def free_entries(
    db: Session, company_id: int, account_ids: list[int], date_from: date, date_to: date
) -> list[AccountingEntry]:
    """Écritures des comptes, entre deux dates, qui ne font partie d'aucune correspondance active."""
    query = (
        select(AccountingEntry)
        .where(
            AccountingEntry.company_id == company_id,
            AccountingEntry.bank_account_id.in_(account_ids),
            # Un effet est comparé à son échéance (09/10/2026) : il est aussi cherché par elle
            or_(
                AccountingEntry.date_ecriture.between(date_from, date_to),
                AccountingEntry.echeance.between(date_from, date_to),
            ),
            AccountingEntry.statut.not_in(STATUTS_FIGES),
            AccountingEntry.id.not_in(_active_entry_ids()),
        )
        .order_by(AccountingEntry.date_ecriture, AccountingEntry.id)
    )
    return list(db.scalars(query))


def rejected_pairs(db: Session, company_id: int) -> set[tuple[int, int]]:
    """Paires (opération, écriture) déjà rejetées par un utilisateur : jamais reproposées."""
    tx_item = aliased(ReconciliationMatchItem)
    entry_item = aliased(ReconciliationMatchItem)
    query = (
        select(tx_item.bank_transaction_id, entry_item.accounting_entry_id)
        .join(ReconciliationMatch, ReconciliationMatch.id == tx_item.match_id)
        .join(entry_item, entry_item.match_id == ReconciliationMatch.id)
        .where(
            ReconciliationMatch.company_id == company_id,
            ReconciliationMatch.statut == "Rejetée",
            tx_item.bank_transaction_id.is_not(None),
            entry_item.accounting_entry_id.is_not(None),
        )
    )
    return {(row[0], row[1]) for row in db.execute(query)}


def automatic_proposals_of_period(
    db: Session, account_ids: list[int], date_from: date, date_to: date
) -> list[ReconciliationMatch]:
    """Propositions automatiques encore en attente dont l'opération est dans la période."""
    query = (
        select(ReconciliationMatch)
        .join(ReconciliationMatchItem, ReconciliationMatchItem.match_id == ReconciliationMatch.id)
        .join(BankTransaction, BankTransaction.id == ReconciliationMatchItem.bank_transaction_id)
        .where(
            ReconciliationMatch.statut == "Proposée",
            ReconciliationMatch.origine == "Automatique",
            BankTransaction.bank_account_id.in_(account_ids),
            BankTransaction.date_operation >= date_from,
            BankTransaction.date_operation <= date_to,
        )
        .options(selectinload(ReconciliationMatch.items))
    )
    return list(db.scalars(query).unique())


def delete_matches(db: Session, match_ids: list[int]) -> None:
    if match_ids:
        db.execute(delete(ReconciliationMatch).where(ReconciliationMatch.id.in_(match_ids)))


def set_transaction_status(db: Session, ids: set[int] | list[int], statut: str) -> None:
    if ids:
        db.execute(update(BankTransaction).where(BankTransaction.id.in_(ids)).values(statut=statut))


def set_entry_status(db: Session, ids: set[int] | list[int], statut: str) -> None:
    if ids:
        db.execute(update(AccountingEntry).where(AccountingEntry.id.in_(ids)).values(statut=statut))


def reset_unmatched_to_check(
    db: Session,
    company_id: int,
    account_ids: list[int],
    tx_from: date,
    tx_to: date,
    entry_from: date,
    entry_to: date,
) -> None:
    """« À vérifier » sans correspondance active (ambiguïté d'un passage précédent) redevient
    « Non rapprochée » avant un nouveau passage du moteur."""
    db.execute(
        update(BankTransaction)
        .where(
            BankTransaction.bank_account_id.in_(account_ids),
            BankTransaction.date_operation >= tx_from,
            BankTransaction.date_operation <= tx_to,
            BankTransaction.statut == "À vérifier",
            BankTransaction.id.not_in(_active_transaction_ids()),
        )
        .values(statut="Non rapprochée")
    )
    db.execute(
        update(AccountingEntry)
        .where(
            AccountingEntry.company_id == company_id,
            AccountingEntry.bank_account_id.in_(account_ids),
            AccountingEntry.date_ecriture >= entry_from,
            AccountingEntry.date_ecriture <= entry_to,
            AccountingEntry.statut == "À vérifier",
            AccountingEntry.id.not_in(_active_entry_ids()),
        )
        .values(statut="Non rapprochée")
    )


def add(db: Session, row: object) -> None:
    db.add(row)


def get_match(db: Session, match_id: int, *, lock: bool = False) -> ReconciliationMatch | None:
    query = (
        select(ReconciliationMatch)
        .where(ReconciliationMatch.id == match_id)
        .options(selectinload(ReconciliationMatch.items))
    )
    if lock:
        query = query.with_for_update(of=ReconciliationMatch)
    return db.scalar(query)


def get_matches(
    db: Session, match_ids: list[int], *, lock: bool = False
) -> list[ReconciliationMatch]:
    query = (
        select(ReconciliationMatch)
        .where(ReconciliationMatch.id.in_(match_ids))
        .options(selectinload(ReconciliationMatch.items))
        .order_by(ReconciliationMatch.id)
    )
    if lock:
        query = query.with_for_update(of=ReconciliationMatch)
    return list(db.scalars(query))


def get_transaction(db: Session, transaction_id: int) -> tuple[BankTransaction, BankAccount] | None:
    row = db.execute(
        select(BankTransaction, BankAccount)
        .join(BankAccount, BankAccount.id == BankTransaction.bank_account_id)
        .where(BankTransaction.id == transaction_id)
    ).first()
    return None if row is None else (row[0], row[1])


def get_entry(db: Session, entry_id: int) -> AccountingEntry | None:
    return db.get(AccountingEntry, entry_id)


def active_matches_of(
    db: Session, *, transaction_id: int | None = None, entry_id: int | None = None
) -> list[ReconciliationMatch]:
    """Correspondances actives qui contiennent l'opération ou l'écriture."""
    conditions = []
    if transaction_id is not None:
        conditions.append(ReconciliationMatchItem.bank_transaction_id == transaction_id)
    if entry_id is not None:
        conditions.append(ReconciliationMatchItem.accounting_entry_id == entry_id)
    query = (
        select(ReconciliationMatch)
        .join(ReconciliationMatchItem, ReconciliationMatchItem.match_id == ReconciliationMatch.id)
        .where(ReconciliationMatchItem.actif.is_(True), or_(*conditions))
        .options(selectinload(ReconciliationMatch.items))
        .with_for_update(of=ReconciliationMatch)
    )
    return list(db.scalars(query).unique())


# --- Lecture des volets ---------------------------------------------------------------------------


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def type_condition(column, regles: tuple[tuple[str, str], ...], type_operation: str):
    """Condition SQL du filtre « Type » (14/10/2026) : Chèque, Effet, Espèces, Virement, ou
    « Autre » (aucun type), avec les mêmes règles que le moteur."""
    if type_operation == AUTRE:
        return or_(column.is_(None), column.op("!~*")(regex_type(regles)))
    return column.op("~*")(regex_type(regles, type_operation))


def transactions_query(
    company_id: int,
    *,
    bank_account_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    q: str | None = None,
    type_operation: str | None = None,
) -> Select:
    """Opérations d'UNE société, filtrées, sans filtre de statut (ni ordre, ni pagination)."""
    query = (
        select(BankTransaction)
        .join(BankAccount, BankAccount.id == BankTransaction.bank_account_id)
        .where(BankAccount.company_id == company_id)
    )
    if bank_account_id is not None:
        query = query.where(BankTransaction.bank_account_id == bank_account_id)
    if date_from is not None:
        query = query.where(BankTransaction.date_operation >= date_from)
    if date_to is not None:
        query = query.where(BankTransaction.date_operation <= date_to)
    if type_operation is not None:
        query = query.where(type_condition(BankTransaction.libelle, TYPES_BANQUE, type_operation))
    if q and q.strip():
        pattern = f"%{_escape_like(q.strip())}%"
        query = query.where(
            or_(
                BankTransaction.libelle.ilike(pattern, escape="\\"),
                BankTransaction.reference.ilike(pattern, escape="\\"),
                # Code de rapprochement (« BP-26-000123 », 13/10/2026)
                BankTransaction.id.in_(
                    ids_with_code(ReconciliationMatchItem.bank_transaction_id, q)
                ),
            )
        )
    return query


def without_status(query: Select, statut: str) -> Select:
    """Le même filtre d'opérations, sans celles qui ont ce statut."""
    return query.where(BankTransaction.statut != statut)


def ambiguous_transactions(
    db: Session,
    company_id: int,
    *,
    bank_account_id: int | None,
    date_from: date | None,
    date_to: date | None,
    offset: int,
    limit: int,
    type_operation: str | None = None,
) -> tuple[int, list[BankTransaction]]:
    """Opérations « À vérifier » sans correspondance active : le moteur a trouvé plusieurs
    candidats trop proches pour en proposer un. Leur nombre sur tout le filtre, et une page, des
    plus récentes aux plus anciennes."""
    query = transactions_query(
        company_id,
        bank_account_id=bank_account_id,
        date_from=date_from,
        date_to=date_to,
        type_operation=type_operation,
    ).where(
        BankTransaction.statut == "À vérifier",
        BankTransaction.id.not_in(_active_transaction_ids()),
    )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    page = query.order_by(
        BankTransaction.date_operation.desc(),
        BankTransaction.statement_id.desc(),
        BankTransaction.ordre.desc(),
        BankTransaction.id.desc(),
    )
    return total, list(db.scalars(page.offset(offset).limit(limit)))


def _active_entry_ids() -> Select:
    return select(ReconciliationMatchItem.accounting_entry_id).where(
        ReconciliationMatchItem.actif.is_(True),
        ReconciliationMatchItem.accounting_entry_id.is_not(None),
    )


def ambiguous_entries(
    db: Session,
    company_id: int,
    *,
    bank_account_id: int | None,
    date_from: date | None,
    date_to: date | None,
    offset: int,
    limit: int | None,
    type_operation: str | None = None,
) -> tuple[int, list[AccountingEntry]]:
    """Écritures « À vérifier » sans correspondance active (15/10/2026) : le moteur a trouvé
    plusieurs opérations trop proches pour en proposer une. Leur nombre sur tout le filtre, et une
    page, des plus récentes aux plus anciennes."""
    query = select(AccountingEntry).where(
        AccountingEntry.company_id == company_id,
        AccountingEntry.statut == "À vérifier",
        AccountingEntry.id.not_in(_active_entry_ids()),
    )
    if bank_account_id is not None:
        query = query.where(AccountingEntry.bank_account_id == bank_account_id)
    if date_from is not None:
        query = query.where(AccountingEntry.date_ecriture >= date_from)
    if date_to is not None:
        query = query.where(AccountingEntry.date_ecriture <= date_to)
    if type_operation:
        query = query.where(type_condition(AccountingEntry.libelle, TYPES_SAGE, type_operation))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    page = query.order_by(AccountingEntry.date_ecriture.desc(), AccountingEntry.id.desc())
    return total, list(db.scalars(page.offset(offset).limit(limit)))


def transactions_comparables(
    db: Session, bank_account_id: int, date_from: date, date_to: date
) -> list[BankTransaction]:
    """Opérations du compte (date d'opération ou de valeur dans la période), hors
    correspondance validée et hors écart : les conditions de `candidate_transactions`, lues en
    une fois pour plusieurs écritures (16/10/2026)."""
    validated_tx_ids = (
        select(ReconciliationMatchItem.bank_transaction_id)
        .join(ReconciliationMatch, ReconciliationMatch.id == ReconciliationMatchItem.match_id)
        .where(
            ReconciliationMatchItem.actif.is_(True),
            ReconciliationMatch.statut == "Validée",
            ReconciliationMatchItem.bank_transaction_id.is_not(None),
        )
    )
    query = select(BankTransaction).where(
        BankTransaction.bank_account_id == bank_account_id,
        or_(
            BankTransaction.date_operation.between(date_from, date_to),
            BankTransaction.date_valeur.between(date_from, date_to),
        ),
        BankTransaction.statut != "Écart",
        BankTransaction.id.not_in(validated_tx_ids),
    )
    return list(db.scalars(query))


def candidate_transactions(
    db: Session,
    entry: AccountingEntry,
    date_from: date,
    date_to: date,
    *,
    large_from: date,
    large_to: date,
    montant: Decimal,
) -> list[BankTransaction]:
    """Opérations du même compte, hors correspondance validée et hors écart : le symétrique de
    `candidate_entries`. Dans la fenêtre courte (date d'opération ou de valeur), ou dans la
    fenêtre large (même n°, 180 jours) au seul montant `montant` : au-delà de la fenêtre courte,
    `comparable` n'admet qu'un chèque ou un effet au même montant (15/10/2026)."""
    validated_tx_ids = (
        select(ReconciliationMatchItem.bank_transaction_id)
        .join(ReconciliationMatch, ReconciliationMatch.id == ReconciliationMatchItem.match_id)
        .where(
            ReconciliationMatchItem.actif.is_(True),
            ReconciliationMatch.statut == "Validée",
            ReconciliationMatchItem.bank_transaction_id.is_not(None),
        )
    )
    query = select(BankTransaction).where(
        BankTransaction.bank_account_id == entry.bank_account_id,
        or_(
            BankTransaction.date_operation.between(date_from, date_to),
            BankTransaction.date_valeur.between(date_from, date_to),
            and_(
                BankTransaction.montant == montant,
                or_(
                    BankTransaction.date_operation.between(large_from, large_to),
                    BankTransaction.date_valeur.between(large_from, large_to),
                ),
            ),
        ),
        BankTransaction.statut != "Écart",
        BankTransaction.id.not_in(validated_tx_ids),
    )
    return list(db.scalars(query))


def active_matches_by_transaction(
    db: Session, transaction_ids: list[int]
) -> dict[int, ReconciliationMatch]:
    """Correspondance active de chaque opération demandée."""
    if not transaction_ids:
        return {}
    rows = db.execute(
        select(ReconciliationMatchItem.bank_transaction_id, ReconciliationMatch)
        .join(ReconciliationMatch, ReconciliationMatch.id == ReconciliationMatchItem.match_id)
        .where(
            ReconciliationMatchItem.actif.is_(True),
            ReconciliationMatchItem.bank_transaction_id.in_(transaction_ids),
        )
        .options(selectinload(ReconciliationMatch.items))
    )
    return {row[0]: row[1] for row in rows}


def count_by_status(db: Session, query: Select) -> dict[str, int]:
    filtered = query.subquery()
    rows = db.execute(select(filtered.c.statut, func.count()).group_by(filtered.c.statut))
    return {row[0]: row[1] for row in rows}


def page_of_transactions(
    db: Session, query: Select, *, statut: str | None, offset: int, limit: int
) -> tuple[int, list[tuple[BankTransaction, str]]]:
    """Nombre d'opérations du filtre et une page, des plus récentes aux plus anciennes."""
    if statut is not None:
        query = query.where(BankTransaction.statut == statut)
    filtered = query.subquery()
    total = db.scalar(select(func.count()).select_from(filtered)) or 0
    rows = db.execute(
        select(BankTransaction, Bank.code)
        .join(filtered, filtered.c.id == BankTransaction.id)
        .join(BankAccount, BankAccount.id == BankTransaction.bank_account_id)
        .join(Bank, Bank.id == BankAccount.bank_id)
        .order_by(
            BankTransaction.date_operation.desc(),
            BankTransaction.statement_id.desc(),
            BankTransaction.ordre.desc(),
            BankTransaction.id.desc(),
        )
        .offset(offset)
        .limit(limit)
    )
    return total, [(row[0], row[1]) for row in rows]


def active_match_by_transaction(
    db: Session, transaction_ids: list[int]
) -> dict[int, ReconciliationMatch]:
    """Correspondance active de chaque opération demandée."""
    if not transaction_ids:
        return {}
    rows = db.execute(
        select(ReconciliationMatchItem.bank_transaction_id, ReconciliationMatch)
        .join(ReconciliationMatch, ReconciliationMatch.id == ReconciliationMatchItem.match_id)
        .where(
            ReconciliationMatchItem.actif.is_(True),
            ReconciliationMatchItem.bank_transaction_id.in_(transaction_ids),
        )
        .options(selectinload(ReconciliationMatch.items))
    )
    return {row[0]: row[1] for row in rows}


def matches_of_period(
    db: Session,
    company_id: int,
    *,
    statut: str,
    bank_account_id: int | None,
    date_from: date | None,
    date_to: date | None,
) -> list[ReconciliationMatch]:
    """Correspondances 1→1 et groupes N→1 (12/10/2026) de la société dont une opération est dans
    le filtre, par date d'opération."""
    query = (
        select(ReconciliationMatch)
        .join(ReconciliationMatchItem, ReconciliationMatchItem.match_id == ReconciliationMatch.id)
        .join(BankTransaction, BankTransaction.id == ReconciliationMatchItem.bank_transaction_id)
        .where(
            ReconciliationMatch.company_id == company_id,
            ReconciliationMatch.statut == statut,
            ReconciliationMatch.type.in_(("1-1", "N-1")),
        )
        .options(selectinload(ReconciliationMatch.items))
        .order_by(BankTransaction.date_operation.desc(), ReconciliationMatch.id.desc())
    )
    if bank_account_id is not None:
        query = query.where(BankTransaction.bank_account_id == bank_account_id)
    if date_from is not None:
        query = query.where(BankTransaction.date_operation >= date_from)
    if date_to is not None:
        query = query.where(BankTransaction.date_operation <= date_to)
    return list(db.scalars(query).unique())


# Statuts d'une correspondance décidée par un utilisateur (historique)
STATUTS_DECIDES = ("Validée", "Rejetée", "Annulée")


def decisions_query(
    company_id: int,
    *,
    bank_account_id: int | None,
    date_from: date | None,
    date_to: date | None,
) -> Select:
    """Identifiants des correspondances décidées de la société dont l'opération est dans le filtre
    (sans filtre de statut, ni ordre, ni pagination)."""
    query = (
        select(ReconciliationMatch.id)
        .join(ReconciliationMatchItem, ReconciliationMatchItem.match_id == ReconciliationMatch.id)
        .join(BankTransaction, BankTransaction.id == ReconciliationMatchItem.bank_transaction_id)
        .where(
            ReconciliationMatch.company_id == company_id,
            ReconciliationMatch.statut.in_(STATUTS_DECIDES),
        )
    )
    if bank_account_id is not None:
        query = query.where(BankTransaction.bank_account_id == bank_account_id)
    if date_from is not None:
        query = query.where(BankTransaction.date_operation >= date_from)
    if date_to is not None:
        query = query.where(BankTransaction.date_operation <= date_to)
    return query.distinct()


def count_decisions_by_status(db: Session, ids_query: Select) -> dict[str, int]:
    ids = ids_query.subquery()
    rows = db.execute(
        select(ReconciliationMatch.statut, func.count())
        .join(ids, ids.c.id == ReconciliationMatch.id)
        .group_by(ReconciliationMatch.statut)
    )
    return {row[0]: row[1] for row in rows}


def page_of_decisions(
    db: Session, ids_query: Select, *, statut: str | None, offset: int, limit: int
) -> tuple[int, list[ReconciliationMatch]]:
    """Nombre de décisions du filtre et une page, de la plus récente à la plus ancienne."""
    if statut is not None:
        ids_query = ids_query.where(ReconciliationMatch.statut == statut)
    ids = ids_query.subquery()
    total = db.scalar(select(func.count()).select_from(ids)) or 0
    query = (
        select(ReconciliationMatch)
        .join(ids, ids.c.id == ReconciliationMatch.id)
        .options(selectinload(ReconciliationMatch.items))
        .order_by(ReconciliationMatch.decide_le.desc(), ReconciliationMatch.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return total, list(db.scalars(query))


def transactions_with_bank(db: Session, ids: set[int]) -> dict[int, tuple[BankTransaction, str]]:
    if not ids:
        return {}
    rows = db.execute(
        select(BankTransaction, Bank.code)
        .join(BankAccount, BankAccount.id == BankTransaction.bank_account_id)
        .join(Bank, Bank.id == BankAccount.bank_id)
        .where(BankTransaction.id.in_(ids))
    )
    return {row[0].id: (row[0], row[1]) for row in rows}


def entries_with_bank(db: Session, ids: set[int]) -> dict[int, tuple[AccountingEntry, str | None]]:
    if not ids:
        return {}
    rows = db.execute(
        select(AccountingEntry, Bank.code)
        .outerjoin(BankAccount, BankAccount.id == AccountingEntry.bank_account_id)
        .outerjoin(Bank, Bank.id == BankAccount.bank_id)
        .where(AccountingEntry.id.in_(ids))
    )
    return {row[0].id: (row[0], row[1]) for row in rows}


def user_names(db: Session, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    return {row[0]: row[1] for row in db.execute(select(User.id, User.nom).where(User.id.in_(ids)))}


def candidate_entries(
    db: Session,
    transaction: BankTransaction,
    company_id: int,
    date_from: date,
    date_to: date,
    *,
    large_from: date | None = None,
    large_to: date | None = None,
) -> list[AccountingEntry]:
    """Écritures du même compte, hors correspondance validée : dans la fenêtre courte, ou dans la
    fenêtre large (même n°, 180 jours) au seul montant opposé, puisque `comparable` n'admet rien
    d'autre au-delà de la fenêtre courte (15/10/2026). Sans fenêtre large : la fenêtre donnée."""
    validated_entry_ids = (
        select(ReconciliationMatchItem.accounting_entry_id)
        .join(ReconciliationMatch, ReconciliationMatch.id == ReconciliationMatchItem.match_id)
        .where(
            ReconciliationMatchItem.actif.is_(True),
            ReconciliationMatch.statut == "Validée",
            ReconciliationMatchItem.accounting_entry_id.is_not(None),
        )
    )
    query = select(AccountingEntry).where(
        and_(
            AccountingEntry.company_id == company_id,
            AccountingEntry.bank_account_id == transaction.bank_account_id,
            # Un effet est comparé à son échéance (09/10/2026) : il est aussi cherché par elle
            or_(
                AccountingEntry.date_ecriture.between(date_from, date_to),
                AccountingEntry.echeance.between(date_from, date_to),
                *(
                    []
                    if large_from is None or large_to is None
                    else [
                        and_(
                            func.coalesce(AccountingEntry.montant_devise, AccountingEntry.montant)
                            == -transaction.montant,
                            or_(
                                AccountingEntry.date_ecriture.between(large_from, large_to),
                                AccountingEntry.echeance.between(large_from, large_to),
                            ),
                        )
                    ]
                ),
            ),
            AccountingEntry.statut != "Écart",
            AccountingEntry.id.not_in(validated_entry_ids),
        )
    )
    return list(db.scalars(query))


def active_matches_by_entry(db: Session, entry_ids: list[int]) -> dict[int, ReconciliationMatch]:
    """Correspondance active de chaque écriture demandée."""
    if not entry_ids:
        return {}
    rows = db.execute(
        select(ReconciliationMatchItem.accounting_entry_id, ReconciliationMatch)
        .join(ReconciliationMatch, ReconciliationMatch.id == ReconciliationMatchItem.match_id)
        .where(
            ReconciliationMatchItem.actif.is_(True),
            ReconciliationMatchItem.accounting_entry_id.in_(entry_ids),
        )
        .options(selectinload(ReconciliationMatch.items))
    )
    return {row[0]: row[1] for row in rows}


# --- Frais bancaires « À comptabiliser » (12/10/2026) ---------------------------------------------
# Pointages des frais bancaires (code interne = `pointage_code` du libellé de la catégorie)
POINTAGES_FRAIS = (
    "COM", "DROIT", "TVA", "FRAIS", "AGIOS", "AGIOS_D_ECHELLE", "INTERET", "TCA",
    "CERTIFICATION_CHEQUE", "FRAIS_RETENUE_A_LA_SOURCE",
)  # fmt: skip
# Sans pointage : mots du libellé (droit de timbre, TVA, commission, frais, agios, intérêts,
# prélèvements)
LIBELLE_FRAIS = (
    r"(DROIT DE TIMBRE|DT D.ENREGISTREMENT|TAXE SUR VALEUR AJOUTEE|^TVA\M|COMMISSION|^COM\M"
    r"|FRAIS|AGIOS|INTERET|PRELEV|PRLV)"
)
# Jamais un frais, quel que soit le pointage choisi (13/10/2026) : ces opérations repassent dans
# « Non rapprochée ». Le libellé l'emporte sur le pointage (« INTERET », « FRAIS »…).
LIBELLE_PAS_FRAIS = r"^\s*(VIREMENT\s+COMMERCIAL|REMISE\s+DOCUMENTAIRE)"


def frais_bancaire():
    """Condition SQL : l'opération est un frais bancaire (par son pointage, sinon son libellé)."""
    pointages = select(PointageType.id).where(PointageType.code.in_(POINTAGES_FRAIS))
    # `pointage_type_id IS NOT NULL` : sans lui, NOT (NULL IN …) vaudrait NULL et une opération sans
    # pointage disparaîtrait aussi de « Non rapprochée »
    return and_(
        or_(
            and_(
                BankTransaction.pointage_type_id.is_not(None),
                BankTransaction.pointage_type_id.in_(pointages),
            ),
            BankTransaction.libelle.op("~*")(LIBELLE_FRAIS),
        ),
        BankTransaction.libelle.op("!~*")(LIBELLE_PAS_FRAIS),
    )


def fee_transaction_ids(db: Session, transaction_ids: list[int]) -> set[int]:
    """Parmi ces opérations, celles qui sont des frais bancaires (règle de « À comptabiliser »)."""
    ids: set[int] = set()
    for debut in range(0, len(transaction_ids), 5000):
        lot = transaction_ids[debut : debut + 5000]
        ids.update(
            db.scalars(
                select(BankTransaction.id).where(BankTransaction.id.in_(lot), frais_bancaire())
            )
        )
    return ids


def a_comptabiliser(db: Session, query: Select) -> tuple[int, Decimal]:
    """Nombre et total (en valeur absolue) des frais bancaires non rapprochés du filtre."""
    filtered = query.where(BankTransaction.statut == "Non rapprochée", frais_bancaire()).subquery()
    row = db.execute(
        select(func.count(), func.coalesce(func.sum(func.abs(filtered.c.montant)), 0))
    ).one()
    return row[0], Decimal(row[1])


# --- Codes de rapprochement (13/10/2026) ------------------------------------------------------------


def next_code_number(db: Session, bank_account_id: int, annee: int) -> int:
    """Numéro suivant du compteur (compte, année), atomique : deux validations simultanées ne
    reçoivent jamais le même numéro."""
    statement = text(
        "INSERT INTO reconciliation_code_counters (bank_account_id, annee, dernier) "
        "VALUES (:compte, :annee, 1) ON CONFLICT (bank_account_id, annee) "
        "DO UPDATE SET dernier = reconciliation_code_counters.dernier + 1 RETURNING dernier"
    )
    return db.execute(statement, {"compte": bank_account_id, "annee": annee}).scalar_one()


def bank_code_of_account(db: Session, bank_account_id: int) -> str:
    return db.execute(
        select(Bank.code)
        .join(BankAccount, BankAccount.bank_id == Bank.id)
        .where(BankAccount.id == bank_account_id)
    ).scalar_one()


def _codes(db: Session, column, ids: set[int] | list[int]) -> dict[int, str]:
    if not ids:
        return {}
    rows = db.execute(
        select(column, ReconciliationMatch.code)
        .join(ReconciliationMatch, ReconciliationMatch.id == ReconciliationMatchItem.match_id)
        .where(
            column.in_(list(ids)),
            ReconciliationMatchItem.actif.is_(True),
            ReconciliationMatch.statut == "Validée",
            ReconciliationMatch.code.is_not(None),
        )
    )
    return {row[0]: row[1] for row in rows}


def codes_of_transactions(db: Session, ids: set[int] | list[int]) -> dict[int, str]:
    """Code du rapprochement validé de chaque opération qui en a un."""
    return _codes(db, ReconciliationMatchItem.bank_transaction_id, ids)


def codes_of_entries(db: Session, ids: set[int] | list[int]) -> dict[int, str]:
    """Code du rapprochement validé de chaque écriture qui en a un."""
    return _codes(db, ReconciliationMatchItem.accounting_entry_id, ids)


def ids_with_code(column, code: str):
    """Sous-requête : lignes (opérations ou écritures) du rapprochement validé portant ce code."""
    return (
        select(column)
        .join(ReconciliationMatch, ReconciliationMatch.id == ReconciliationMatchItem.match_id)
        .where(
            ReconciliationMatchItem.actif.is_(True),
            ReconciliationMatch.statut == "Validée",
            func.upper(ReconciliationMatch.code) == code.strip().upper(),
        )
    )


def validated_matches(db: Session, ids_query: Select) -> list[ReconciliationMatch]:
    """Toutes les correspondances validées du filtre (export du lettrage, 14/10/2026), par code."""
    ids = ids_query.where(ReconciliationMatch.statut == "Validée").subquery()
    return list(
        db.scalars(
            select(ReconciliationMatch)
            .join(ids, ids.c.id == ReconciliationMatch.id)
            .options(selectinload(ReconciliationMatch.items))
            .order_by(ReconciliationMatch.code, ReconciliationMatch.id)
        )
    )
