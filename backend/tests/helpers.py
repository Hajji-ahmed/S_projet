"""Constructeurs de données de test et vérification des rejets par la base."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from itertools import count

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AccountingEntry,
    Bank,
    BankAccount,
    BankStatement,
    BankTransaction,
    Company,
    Currency,
    ForecastCategory,
    User,
)

_sequence = count(1)


def assert_rejected(db: Session, message: str, *objects: object, sql: str | None = None) -> None:
    """Vérifie que la base REFUSE l'opération, avec une erreur qui cite `message` (nom de contrainte...).

    Les objets sont enregistrés, ou le SQL exécuté, dans un point de sauvegarde annulé au refus :
    la session reste utilisable et les données préparées par le test sont conservées.
    """
    with pytest.raises(IntegrityError) as excinfo:
        with db.begin_nested():
            if objects:
                db.add_all(objects)
                db.flush()
            if sql:
                db.execute(text(sql))
    assert message in str(excinfo.value.orig), f"attendu « {message} » dans : {excinfo.value.orig}"


def save(db: Session, *objects):
    """Enregistre les objets et retourne le premier (ou l'unique)."""
    db.add_all(objects)
    db.flush()
    return objects[0]


def make_currencies(db: Session) -> None:
    for code, libelle in (("MAD", "Dirham"), ("EUR", "Euro"), ("USD", "Dollar")):
        if db.get(Currency, code) is None:
            db.add(Currency(code=code, libelle=libelle))
    db.flush()


def build_company(**over) -> Company:
    n = next(_sequence)
    return Company(**{"code": f"C{n}", "nom": f"Société {n}", **over})


def build_bank(**over) -> Bank:
    n = next(_sequence)
    return Bank(**{"code": f"B{n}", "nom": f"Banque {n}", **over})


def build_account(company: Company, bank: Bank, **over) -> BankAccount:
    n = next(_sequence)
    return BankAccount(
        **{
            "company_id": company.id,
            "bank_id": bank.id,
            "libelle": "Compte test",
            "numero": f"N{n}",
            "devise": "MAD",
            **over,
        }
    )


def build_transaction(statement: BankStatement, **over) -> BankTransaction:
    """Transaction de 100 au crédit. Qui change débit ou crédit doit aussi fournir `montant`."""
    return BankTransaction(
        **{
            "statement_id": statement.id,
            "bank_account_id": statement.bank_account_id,
            "date_operation": date(2026, 9, 24),
            "libelle": "VIR CLIENT ABC",
            "debit": Decimal("0"),
            "credit": Decimal("100"),
            "montant": Decimal("100"),
            "hash_ligne": f"h{next(_sequence)}",
            **over,
        }
    )


def build_entry(company: Company, **over) -> AccountingEntry:
    """Écriture de 100 au crédit. Qui change débit ou crédit doit aussi fournir `montant`."""
    return AccountingEntry(
        **{
            "company_id": company.id,
            "date_ecriture": date(2026, 9, 24),
            "libelle": "REG FACT-458",
            "debit": Decimal("0"),
            "credit": Decimal("100"),
            "montant": Decimal("100"),
            "hash_ligne": f"e{next(_sequence)}",
            **over,
        }
    )


def build_user(**over) -> User:
    n = next(_sequence)
    return User(
        **{
            "nom": f"Utilisateur {n}",
            "email": f"u{n}@example.com",
            "mot_de_passe_hash": "x",
            **over,
        }
    )


@dataclass
class World:
    """Jeu de données minimal : une société, une banque, un compte, un relevé, un utilisateur."""

    company: Company
    bank: Bank
    account: BankAccount
    statement: BankStatement
    user: User
    category: ForecastCategory


def make_world(db: Session) -> World:
    make_currencies(db)
    company = save(db, build_company())
    bank = save(db, build_bank())
    account = save(db, build_account(company, bank))
    statement = save(db, BankStatement(bank_account_id=account.id))
    user = save(db, build_user())
    category = db.scalar(select(ForecastCategory).filter_by(code="TEST"))
    if category is None:
        category = save(db, ForecastCategory(code="TEST", libelle="Test"))
    return World(company, bank, account, statement, user, category)
