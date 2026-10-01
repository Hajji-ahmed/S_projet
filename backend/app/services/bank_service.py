"""Référentiel des banques : ce sont les colonnes des tableaux Banques, Devises et Prévisions.

Règles :
- le code n'est plus modifiable après la création (les seeds retrouvent les banques par leur code) ;
- aucune suppression : une banque se désactive ;
- une banque qui a encore des comptes actifs ne peut pas être désactivée ;
- chaque écriture est tracée dans `audit_logs`, dans la même transaction.
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Bank
from app.repositories import bank_repository
from app.services import audit_service
from app.services.errors import ConflictError, NotFoundError

MAX_DISPLAY_ORDER = 999
EDITABLE_FIELDS = ("nom", "logo", "ordre_affichage")


@dataclass(frozen=True)
class BankSummary:
    bank: Bank
    nb_comptes_actifs: int


def _snapshot(bank: Bank, fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: getattr(bank, field) for field in fields}


def _get_or_404(db: Session, bank_id: int) -> Bank:
    bank = bank_repository.get(db, bank_id)
    if bank is None:
        raise NotFoundError("Banque introuvable.")
    return bank


def _summary(db: Session, bank: Bank) -> BankSummary:
    return BankSummary(bank, bank_repository.active_account_counts(db).get(bank.id, 0))


def list_banks(db: Session, company_id: int | None = None) -> list[BankSummary]:
    """`company_id` : compter seulement les comptes de cette société (société active de l'écran)."""
    counts = bank_repository.active_account_counts(db, company_id)
    return [BankSummary(bank, counts.get(bank.id, 0)) for bank in bank_repository.list_banks(db)]


def get_bank(db: Session, bank_id: int) -> BankSummary:
    return _summary(db, _get_or_404(db, bank_id))


def create_bank(
    db: Session,
    *,
    code: str,
    nom: str,
    logo: str | None,
    ordre_affichage: int | None,
    acteur_id: int,
    ip: str | None = None,
) -> BankSummary:
    code = code.strip().upper()
    if bank_repository.get_by_code(db, code) is not None:
        raise ConflictError(f"Le code {code} est déjà utilisé par une autre banque.")

    if ordre_affichage is None:  # par défaut : en dernière position
        ordre_affichage = min((bank_repository.max_display_order(db) or 0) + 1, MAX_DISPLAY_ORDER)

    bank = Bank(code=code, nom=nom.strip(), logo=logo, ordre_affichage=ordre_affichage, actif=True)
    try:
        bank_repository.add(db, bank)
    except IntegrityError as error:  # création simultanée du même code
        db.rollback()
        raise ConflictError(f"Le code {code} est déjà utilisé par une autre banque.") from error

    audit_service.log(
        db,
        user_id=acteur_id,
        action="creation_banque",
        entite="bank",
        entite_id=bank.id,
        apres=_snapshot(bank, ("code", *EDITABLE_FIELDS, "actif")),
        ip=ip,
    )
    db.commit()
    return BankSummary(bank, 0)


def update_bank(
    db: Session,
    bank_id: int,
    *,
    nom: str,
    logo: str | None,
    ordre_affichage: int,
    acteur_id: int,
    ip: str | None = None,
) -> BankSummary:
    """Modifie nom, logo et ordre. Seuls les champs réellement changés sont tracés."""
    bank = _get_or_404(db, bank_id)
    new_values = {"nom": nom.strip(), "logo": logo, "ordre_affichage": ordre_affichage}
    changed = tuple(field for field, value in new_values.items() if getattr(bank, field) != value)

    if changed:
        avant = _snapshot(bank, changed)
        for field in changed:
            setattr(bank, field, new_values[field])
        audit_service.log(
            db,
            user_id=acteur_id,
            action="modification_banque",
            entite="bank",
            entite_id=bank.id,
            avant=avant,
            apres=_snapshot(bank, changed),
            ip=ip,
        )
        db.commit()
    return _summary(db, bank)


def set_bank_status(
    db: Session, bank_id: int, *, actif: bool, acteur_id: int, ip: str | None = None
) -> BankSummary:
    bank = _get_or_404(db, bank_id)
    if bank.actif == actif:
        return _summary(db, bank)

    if not actif:
        active_accounts = bank_repository.active_account_counts(db).get(bank.id, 0)
        if active_accounts:
            pluriel = "s" if active_accounts > 1 else ""
            raise ConflictError(
                f"Impossible de désactiver {bank.code} : {active_accounts} compte{pluriel} "
                f"actif{pluriel}. Désactivez d'abord ses comptes."
            )

    bank.actif = actif
    audit_service.log(
        db,
        user_id=acteur_id,
        action="reactivation_banque" if actif else "desactivation_banque",
        entite="bank",
        entite_id=bank.id,
        avant={"actif": not actif},
        apres={"actif": actif},
        ip=ip,
    )
    db.commit()
    return _summary(db, bank)
