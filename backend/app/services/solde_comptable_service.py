"""Solde comptable (Sage) d'un compte bancaire (décision du 26/10/2026).

    Solde comptable = solde d'ouverture (saisi à sa date)
                    + débits − crédits des écritures après cette date, jusqu'à la date choisie

C'est le sens du grand livre Sage pour un compte de banque : débiteur (positif) = argent en banque,
comme le solde du relevé. Toutes les écritures du compte comptent (Sage, frais SIMTIS, saisies
manuelles) ; une écriture SIMTIS pas encore exportée vers Sage est comptée à part pour expliquer un
écart avec Sage. Un compte EUR / USD a aussi son solde dans sa devise (colonne « Devise » de Sage).
Sans solde d'ouverture, seul le mouvement est donné : un départ à 0 n'est jamais inventé.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import BankAccount
from app.repositories import account_repository, accounting_repository, reconciliation_repository
from app.services import audit_service
from app.services.errors import ConflictError, NotFoundError
from app.services.position_banques_service import soldes_par_compte
from app.services.position_service import PREMIERE_DATE_SOLDE, business_today, solde_connu

ZERO = Decimal("0.00")
CENTIME = Decimal("0.01")


@dataclass(frozen=True)
class Mouvements:
    debit: Decimal
    credit: Decimal
    # Somme du montant devise signé comme dans SIMTIS (crédit − débit) ; None : aucun
    devise: Decimal | None
    nb_ecritures: int
    nb_non_exportees: int


@dataclass(frozen=True)
class SoldeComptable:
    account: BankAccount
    jour: date
    ouverture: Decimal | None
    date_ouverture: date | None
    debit: Decimal
    credit: Decimal
    solde: Decimal | None
    ouverture_devise: Decimal | None
    solde_devise: Decimal | None
    solde_bancaire: Decimal | None
    date_solde_bancaire: date | None
    # Solde bancaire − solde comptable, dans la devise du compte ; None s'il manque l'un des deux
    ecart: Decimal | None
    nb_ecritures: int
    nb_non_exportees: int


def solde_comptable(ouverture: Decimal | None, debit: Decimal, credit: Decimal) -> Decimal | None:
    """Règle pure : ouverture + débits − crédits ; None sans solde d'ouverture."""
    return None if ouverture is None else ouverture + debit - credit


def _calcul(
    account: BankAccount, jour: date, mvt: Mouvements, banque: tuple[date, Decimal] | None
) -> SoldeComptable:
    solde = solde_comptable(account.solde_comptable_ouverture, mvt.debit, mvt.credit)
    solde_devise = None
    if account.devise != "MAD" and account.solde_comptable_ouverture_devise is not None:
        # Le montant devise est signé comme le montant SIMTIS (crédit − débit) : on le retranche
        solde_devise = account.solde_comptable_ouverture_devise - (mvt.devise or ZERO)
    compare = solde if account.devise == "MAD" else solde_devise
    ecart = banque[1] - compare if banque and compare is not None else None
    return SoldeComptable(
        account=account,
        jour=jour,
        ouverture=account.solde_comptable_ouverture,
        date_ouverture=account.date_solde_comptable,
        debit=mvt.debit,
        credit=mvt.credit,
        solde=solde,
        ouverture_devise=account.solde_comptable_ouverture_devise,
        solde_devise=solde_devise,
        solde_bancaire=banque[1] if banque else None,
        date_solde_bancaire=banque[0] if banque else None,
        ecart=ecart,
        nb_ecritures=mvt.nb_ecritures,
        nb_non_exportees=mvt.nb_non_exportees,
    )


def soldes(
    db: Session, company_id: int, jour: date | None, bank_account_id: int | None = None
) -> list[SoldeComptable]:
    """Solde comptable de chaque compte actif qui a un journal Sage, au `jour` (aujourd'hui par
    défaut, jamais après)."""
    company = account_repository.get_company(db, company_id)
    if company is None or not company.actif:
        raise NotFoundError("Société introuvable.")
    jour = min(jour or business_today(), business_today())
    comptes = [
        a
        for a in reconciliation_repository.company_accounts(db, company.id, bank_account_id)
        if a.actif and a.journal_sage
    ]
    comptes.sort(key=lambda a: (a.bank.ordre_affichage, a.devise, a.id))
    bancaires = soldes_par_compte(db, [a.id for a in comptes], jour)
    resultat = []
    for account in comptes:
        mvt = accounting_repository.mouvements_comptables(
            db, account.id, apres=account.date_solde_comptable, jusqu_au=jour
        )
        resultat.append(_calcul(account, jour, mvt, solde_connu(bancaires[account.id], jour)))
    return resultat


def _montant(valeur: Decimal | None) -> Decimal | None:
    return None if valeur is None else valeur.quantize(CENTIME)


def set_ouverture(
    db: Session,
    account_id: int,
    *,
    date_ouverture: date | None,
    solde: Decimal | None,
    solde_devise: Decimal | None,
    acteur_id: int,
    ip: str | None,
) -> BankAccount:
    """Saisit (ou efface, tout à None) le solde comptable d'ouverture d'un compte, avec sa date."""
    account = account_repository.get(db, account_id)
    if account is None:
        raise NotFoundError("Compte introuvable.")
    if (date_ouverture is None) != (solde is None):
        raise ConflictError("Indiquez à la fois la date et le solde comptable d'ouverture.")
    if date_ouverture is not None and not (
        PREMIERE_DATE_SOLDE <= date_ouverture <= business_today()
    ):
        raise ConflictError(
            "La date du solde d'ouverture doit être entre le 01/01/2000 et aujourd'hui."
        )
    if account.devise == "MAD":
        solde_devise = None
    elif solde is not None and solde_devise is None:
        raise ConflictError(f"Indiquez aussi le solde d'ouverture en {account.devise}.")
    avant = {
        "date_solde_comptable": account.date_solde_comptable,
        "solde_comptable_ouverture": account.solde_comptable_ouverture,
        "solde_comptable_ouverture_devise": account.solde_comptable_ouverture_devise,
    }
    account.date_solde_comptable = date_ouverture
    account.solde_comptable_ouverture = _montant(solde)
    account.solde_comptable_ouverture_devise = _montant(solde_devise)
    apres = {
        "date_solde_comptable": account.date_solde_comptable,
        "solde_comptable_ouverture": account.solde_comptable_ouverture,
        "solde_comptable_ouverture_devise": account.solde_comptable_ouverture_devise,
    }
    if apres != avant:
        audit_service.log(
            db,
            user_id=acteur_id,
            action="solde_comptable_ouverture",
            entite="bank_account",
            entite_id=account.id,
            avant=avant,
            apres=apres,
            ip=ip,
        )
    db.commit()
    return account
