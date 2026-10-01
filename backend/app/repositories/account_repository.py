from sqlalchemy import case, select
from sqlalchemy.orm import Session, joinedload

from app.models import Bank, BankAccount, Company, Currency


def list_companies(db: Session) -> list[Company]:
    return list(db.scalars(select(Company).where(Company.actif.is_(True)).order_by(Company.id)))


def list_currencies(db: Session) -> list[Currency]:
    # Le dirham d'abord, puis les devises par ordre alphabétique
    return list(
        db.scalars(
            select(Currency).order_by(case((Currency.code == "MAD", 0), else_=1), Currency.code)
        )
    )


def get_company(db: Session, company_id: int) -> Company | None:
    return db.get(Company, company_id)


def get_bank(db: Session, bank_id: int) -> Bank | None:
    return db.get(Bank, bank_id)


def get_currency(db: Session, code: str) -> Currency | None:
    return db.get(Currency, code)


def list_accounts(
    db: Session,
    *,
    company_id: int,
    bank_id: int | None = None,
    devise: str | None = None,
    actif: bool | None = None,
) -> list[BankAccount]:
    """Comptes d'UNE société, dans l'ordre des colonnes de banques."""
    query = (
        select(BankAccount)
        .join(Bank, Bank.id == BankAccount.bank_id)
        .options(joinedload(BankAccount.bank))
        .where(BankAccount.company_id == company_id)
        .order_by(
            Bank.ordre_affichage,
            Bank.code,
            case((BankAccount.devise == "MAD", 0), else_=1),
            BankAccount.devise,
            BankAccount.type_compte,
            BankAccount.libelle,
        )
    )
    if bank_id is not None:
        query = query.where(BankAccount.bank_id == bank_id)
    if devise is not None:
        query = query.where(BankAccount.devise == devise)
    if actif is not None:
        query = query.where(BankAccount.actif.is_(actif))
    return list(db.scalars(query))


def get(db: Session, account_id: int) -> BankAccount | None:
    return db.get(BankAccount, account_id)


def get_by_numero(db: Session, numero: str) -> BankAccount | None:
    return db.scalar(select(BankAccount).where(BankAccount.numero == numero))


def find_active_in_slot(
    db: Session, *, company_id: int, bank_id: int, devise: str, type_compte: str
) -> BankAccount | None:
    """Le compte actif qui occupe déjà la place (société, banque, devise, type), s'il existe."""
    query = select(BankAccount).where(
        BankAccount.company_id == company_id,
        BankAccount.bank_id == bank_id,
        BankAccount.devise == devise,
        BankAccount.type_compte == type_compte,
        BankAccount.actif.is_(True),
    )
    return db.scalar(query)


def add(db: Session, account: BankAccount) -> BankAccount:
    db.add(account)
    db.flush()
    return account
