"""Comptes bancaires des sociétés.

Règles :
- une réponse ne contient jamais les comptes de deux sociétés ;
- société, banque et devise ne changent plus après la création (l'historique des soldes en dépend) ;
- une société a au plus UN compte actif par banque, devise et type (une cellule des tableaux) ;
- un compte DH convertible est en MAD ;
- aucune suppression : un compte se désactive ; chaque écriture est tracée dans `audit_logs`.

Le taux d'intérêt est saisi en pourcentage (4,5) et stocké en fraction (0,045), en `Decimal`.
"""

from decimal import Decimal
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import BankAccount, Company, Currency
from app.repositories import account_repository
from app.services import audit_service
from app.services.errors import ConflictError, NotFoundError

HUNDRED = Decimal(100)
# Précision des colonnes : NUMERIC(18,2) pour les montants, NUMERIC(18,6) pour les taux
CENT = Decimal("0.01")
RATE_STEP = Decimal("0.000001")
EDITABLE_FIELDS = (
    "libelle",
    "numero",
    "type_compte",
    "compte_comptable",
    "credit_autorise",
    "taux_interet",
    "journal_sage",
)
TYPE_LABELS = {"Courant": "courant", "DH convertible": "DH convertible"}


def pct_to_fraction(pct: Decimal | None) -> Decimal | None:
    """4.5 → 0.045000, à la précision de la colonne."""
    return None if pct is None else (pct / HUNDRED).quantize(RATE_STEP)


def to_amount(value: Decimal) -> Decimal:
    """Montant à la précision de la colonne (500000 → 500000.00)."""
    return value.quantize(CENT)


def fraction_to_pct(fraction: Decimal | None) -> Decimal | None:
    """0.045000 → 4.5 (sans zéros inutiles, jamais en notation scientifique)."""
    if fraction is None:
        return None
    text = format(fraction * HUNDRED, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return Decimal(text)


def normalize_numero(numero: str) -> str:
    """Le RIB est comparé et stocké sans espaces, en majuscules."""
    return "".join(numero.split()).upper()


def list_companies(db: Session) -> list[Company]:
    return account_repository.list_companies(db)


def list_currencies(db: Session) -> list[Currency]:
    return account_repository.list_currencies(db)


def list_accounts(
    db: Session,
    *,
    company_id: int,
    bank_id: int | None = None,
    devise: str | None = None,
    actif: bool | None = None,
) -> list[BankAccount]:
    return account_repository.list_accounts(
        db, company_id=company_id, bank_id=bank_id, devise=devise, actif=actif
    )


def get_account(db: Session, account_id: int) -> BankAccount:
    account = account_repository.get(db, account_id)
    if account is None:
        raise NotFoundError("Compte introuvable.")
    return account


def _snapshot(account: BankAccount, fields: tuple[str, ...]) -> dict[str, Any]:
    """Valeurs pour l'audit, à la précision des colonnes (comme elles sont stockées)."""
    values = {field: getattr(account, field) for field in fields}
    if values.get("credit_autorise") is not None:
        values["credit_autorise"] = to_amount(values["credit_autorise"])
    if values.get("taux_interet") is not None:
        values["taux_interet"] = values["taux_interet"].quantize(RATE_STEP)
    return values


def _check_numero_free(db: Session, numero: str, account_id: int | None = None) -> None:
    existing = account_repository.get_by_numero(db, numero)
    if existing is not None and existing.id != account_id:
        raise ConflictError(f"Le numéro {numero} est déjà utilisé par un autre compte.")


def _check_slot_free(
    db: Session,
    *,
    company: Company,
    bank_code: str,
    bank_id: int,
    devise: str,
    type_compte: str,
    account_id: int | None = None,
) -> None:
    occupant = account_repository.find_active_in_slot(
        db, company_id=company.id, bank_id=bank_id, devise=devise, type_compte=type_compte
    )
    if occupant is not None and occupant.id != account_id:
        raise ConflictError(
            f"{bank_code} a déjà un compte {TYPE_LABELS[type_compte]} en {devise} actif pour "
            f"{company.nom}. Désactivez-le d'abord pour en ouvrir un autre."
        )


def _check_journal_free(
    db: Session, *, company_id: int, journal: str | None, account_id: int | None = None
) -> None:
    """Un journal Sage ne sert qu'à un compte actif par société (P10)."""
    if journal is None:
        return
    occupant = account_repository.find_active_by_journal(db, company_id=company_id, journal=journal)
    if occupant is not None and occupant.id != account_id:
        raise ConflictError(
            f"Le journal Sage {journal} est déjà celui du compte "
            f"{occupant.bank.code} {occupant.devise} de cette société."
        )


def _check_dh_convertible(type_compte: str, devise: str) -> None:
    if type_compte == "DH convertible" and devise != "MAD":
        raise ConflictError("Un compte DH convertible doit être en MAD.")


def create_account(
    db: Session,
    *,
    company_id: int,
    bank_id: int,
    libelle: str,
    numero: str,
    devise: str,
    type_compte: str,
    compte_comptable: str | None,
    credit_autorise: Decimal,
    taux_interet_pct: Decimal | None,
    acteur_id: int,
    ip: str | None = None,
    journal_sage: str | None = None,
) -> BankAccount:
    company = account_repository.get_company(db, company_id)
    if company is None or not company.actif:
        raise NotFoundError("Société introuvable.")
    bank = account_repository.get_bank(db, bank_id)
    if bank is None:
        raise NotFoundError("Banque introuvable.")
    if not bank.actif:
        raise ConflictError(f"La banque {bank.code} est inactive : réactivez-la d'abord.")
    if account_repository.get_currency(db, devise) is None:
        raise ConflictError(f"Devise inconnue : {devise}.")
    _check_dh_convertible(type_compte, devise)

    numero = normalize_numero(numero)
    _check_numero_free(db, numero)
    _check_slot_free(
        db,
        company=company,
        bank_code=bank.code,
        bank_id=bank.id,
        devise=devise,
        type_compte=type_compte,
    )
    _check_journal_free(db, company_id=company.id, journal=journal_sage)

    account = BankAccount(
        company_id=company.id,
        bank_id=bank.id,
        libelle=libelle.strip(),
        numero=numero,
        devise=devise,
        type_compte=type_compte,
        compte_comptable=compte_comptable,
        journal_sage=journal_sage,
        credit_autorise=to_amount(credit_autorise),
        taux_interet=pct_to_fraction(taux_interet_pct),
        actif=True,
    )
    try:
        account_repository.add(db, account)
    except IntegrityError as error:  # création simultanée du même compte
        db.rollback()
        raise ConflictError("Ce compte existe déjà (numéro ou banque déjà utilisés).") from error

    audit_service.log(
        db,
        user_id=acteur_id,
        action="creation_compte",
        entite="bank_account",
        entite_id=account.id,
        apres=_snapshot(account, ("company_id", "bank_id", "devise", *EDITABLE_FIELDS, "actif")),
        ip=ip,
    )
    db.commit()
    return account


def update_account(
    db: Session,
    account_id: int,
    *,
    libelle: str,
    numero: str,
    type_compte: str,
    compte_comptable: str | None,
    credit_autorise: Decimal,
    taux_interet_pct: Decimal | None,
    acteur_id: int,
    ip: str | None = None,
    journal_sage: str | None = None,
) -> BankAccount:
    """Société, banque et devise ne sont pas modifiables. Seuls les champs changés sont tracés."""
    account = get_account(db, account_id)
    new_values = {
        "libelle": libelle.strip(),
        "numero": normalize_numero(numero),
        "type_compte": type_compte,
        "compte_comptable": compte_comptable,
        "credit_autorise": to_amount(credit_autorise),
        "taux_interet": pct_to_fraction(taux_interet_pct),
        "journal_sage": journal_sage,
    }
    changed = tuple(
        field for field, value in new_values.items() if getattr(account, field) != value
    )
    if not changed:
        return account

    if "numero" in changed:
        _check_numero_free(db, new_values["numero"], account.id)
    if "type_compte" in changed:
        _check_dh_convertible(type_compte, account.devise)
        if account.actif:
            _check_slot_free(
                db,
                company=account.company,
                bank_code=account.bank.code,
                bank_id=account.bank_id,
                devise=account.devise,
                type_compte=type_compte,
                account_id=account.id,
            )

    if "journal_sage" in changed and account.actif:
        _check_journal_free(
            db, company_id=account.company_id, journal=journal_sage, account_id=account.id
        )

    avant = _snapshot(account, changed)
    for field in changed:
        setattr(account, field, new_values[field])
    audit_service.log(
        db,
        user_id=acteur_id,
        action="modification_compte",
        entite="bank_account",
        entite_id=account.id,
        avant=avant,
        apres=_snapshot(account, changed),
        ip=ip,
    )
    db.commit()
    return account


def set_account_status(
    db: Session, account_id: int, *, actif: bool, acteur_id: int, ip: str | None = None
) -> BankAccount:
    account = get_account(db, account_id)
    if account.actif == actif:
        return account

    if actif:
        if not account.bank.actif:
            raise ConflictError(
                f"La banque {account.bank.code} est inactive : réactivez-la avant ce compte."
            )
        _check_slot_free(
            db,
            company=account.company,
            bank_code=account.bank.code,
            bank_id=account.bank_id,
            devise=account.devise,
            type_compte=account.type_compte,
            account_id=account.id,
        )
        _check_journal_free(
            db, company_id=account.company_id, journal=account.journal_sage, account_id=account.id
        )

    account.actif = actif
    audit_service.log(
        db,
        user_id=acteur_id,
        action="reactivation_compte" if actif else "desactivation_compte",
        entite="bank_account",
        entite_id=account.id,
        avant={"actif": not actif},
        apres={"actif": actif},
        ip=ip,
    )
    db.commit()
    return account


ATTRIBUTS_AUDIT_SUPPRESSION = (
    "company_id",
    "bank_id",
    "libelle",
    "numero",
    "devise",
    "type_compte",
    "compte_comptable",
    "journal_sage",
    "credit_autorise",
    "taux_interet",
    "actif",
)


def accounts_with_history(db: Session, account_ids: list[int]) -> set[int]:
    return account_repository.accounts_with_history(db, account_ids)


def delete_account(db: Session, account_id: int, *, acteur_id: int, ip: str | None = None) -> None:
    """Efface un compte sans historique (aucun relevé, opération, écriture, import ni contrôle de
    solde), avec ses soldes saisis à la main. Un compte qui a un historique ne peut être que
    désactivé (décision du 08/10/2026)."""
    account = get_account(db, account_id)
    if account_repository.accounts_with_history(db, [account.id]):
        raise ConflictError(
            "Ce compte a un historique (relevés, écritures ou imports) : il ne peut être que "
            "désactivé."
        )
    avant = {
        **_snapshot(account, ATTRIBUTS_AUDIT_SUPPRESSION),
        "banque": account.bank.code,
        "soldes_saisis_effaces": account_repository.manual_balances_count(db, account.id),
    }
    account_repository.delete_account(db, account)
    audit_service.log(
        db,
        user_id=acteur_id,
        action="suppression_compte",
        entite="bank_account",
        entite_id=account_id,
        avant=avant,
        ip=ip,
    )
    db.commit()
