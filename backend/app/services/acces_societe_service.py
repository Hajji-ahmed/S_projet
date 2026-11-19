"""Accès par société (décision du 19/11/2026).

L'administrateur peut limiter une personne à certaines sociétés (`user_companies`). Aucune société
cochée = toutes ; le rôle Administrateur voit toujours tout (`CurrentUser.societes` vaut None).

Le contrôle se fait à deux endroits :
- `verifier_parametres` (dépendance de `protected_router`) : tout paramètre de chemin ou de requête
  nommé dans `RESOLVEURS` (company_id, account_id, transaction_id...) est ramené à sa société et
  vérifié, pour toutes les routes, y compris les futures ;
- les endpoints qui reçoivent une société, un compte ou des ids dans un corps JSON ou un formulaire
  appellent `verifier`, `verifier_comptes`, `verifier_operations`... eux-mêmes.

Un id inconnu passe : le service répond ensuite 404 comme avant.
"""

from collections.abc import Callable, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AccountingEntry,
    BankAccount,
    BankStatement,
    BankTransaction,
    ImportBatch,
    ReconciliationMatch,
)
from app.services.auth_service import CurrentUser
from app.services.errors import ForbiddenError

REFUS = "Accès refusé : cette société ne fait pas partie de vos sociétés autorisées."


def verifier(user: CurrentUser, company_id: int | None) -> None:
    if company_id is not None and not user.peut_voir(company_id):
        raise ForbiddenError(REFUS)


def _societes(db: Session, colonne, cle, ids: Iterable[int]) -> set[int]:
    ids = set(ids)
    if not ids:
        return set()
    return set(db.scalars(select(colonne).where(cle.in_(ids)).distinct()))


def _verifier_toutes(user: CurrentUser, societes: Iterable[int]) -> None:
    if user.societes is None:
        return
    for company_id in societes:
        verifier(user, company_id)


def verifier_comptes(db: Session, user: CurrentUser, ids: Iterable[int | None]) -> None:
    if user.societes is None:
        return
    _verifier_toutes(
        user,
        _societes(db, BankAccount.company_id, BankAccount.id, (i for i in ids if i is not None)),
    )


def verifier_releves(db: Session, user: CurrentUser, ids: Iterable[int]) -> None:
    if user.societes is None:
        return
    query_ids = set(ids)
    if not query_ids:
        return
    societes = db.scalars(
        select(BankAccount.company_id)
        .join(BankStatement, BankStatement.bank_account_id == BankAccount.id)
        .where(BankStatement.id.in_(query_ids))
        .distinct()
    )
    _verifier_toutes(user, societes)


def verifier_operations(db: Session, user: CurrentUser, ids: Iterable[int | None]) -> None:
    if user.societes is None:
        return
    query_ids = {i for i in ids if i is not None}
    if not query_ids:
        return
    societes = db.scalars(
        select(BankAccount.company_id)
        .join(BankTransaction, BankTransaction.bank_account_id == BankAccount.id)
        .where(BankTransaction.id.in_(query_ids))
        .distinct()
    )
    _verifier_toutes(user, societes)


def verifier_ecritures(db: Session, user: CurrentUser, ids: Iterable[int | None]) -> None:
    if user.societes is None:
        return
    _verifier_toutes(
        user,
        _societes(
            db, AccountingEntry.company_id, AccountingEntry.id, (i for i in ids if i is not None)
        ),
    )


def verifier_correspondances(db: Session, user: CurrentUser, ids: Iterable[int]) -> None:
    if user.societes is None:
        return
    _verifier_toutes(
        user, _societes(db, ReconciliationMatch.company_id, ReconciliationMatch.id, ids)
    )


def verifier_lots(db: Session, user: CurrentUser, ids: Iterable[int]) -> None:
    if user.societes is None:
        return
    _verifier_toutes(user, _societes(db, ImportBatch.company_id, ImportBatch.id, ids))


def _verifier_societes(_db: Session, user: CurrentUser, ids: Iterable[int]) -> None:
    for company_id in ids:
        verifier(user, company_id)


# Nom du paramètre de chemin ou de requête → contrôle de sa société
RESOLVEURS: dict[str, Callable[[Session, CurrentUser, Iterable[int]], None]] = {
    "company_id": _verifier_societes,
    "account_id": verifier_comptes,
    "bank_account_id": verifier_comptes,
    "statement_id": verifier_releves,
    "transaction_id": verifier_operations,
    "entry_id": verifier_ecritures,
    "match_id": verifier_correspondances,
    "batch_id": verifier_lots,
}


def verifier_parametres(db: Session, user: CurrentUser, parametres: dict[str, list[str]]) -> None:
    """Vérifie chaque paramètre connu ; une valeur qui n'est pas un entier est laissée à la
    validation de la route (422)."""
    if user.societes is None:
        return
    for nom, valeurs in parametres.items():
        resolveur = RESOLVEURS.get(nom)
        if resolveur is None:
            continue
        ids = [int(valeur) for valeur in valeurs if valeur.lstrip("-").isdigit()]
        if ids:
            resolveur(db, user, ids)
