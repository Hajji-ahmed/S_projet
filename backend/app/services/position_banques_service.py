"""Tableaux Banques (P8.1) et Devises (soldes EUR / USD) : lit la base et applique les règles pures
de `position_service`."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Bank, BankAccount, Company
from app.repositories import account_repository, position_repository
from app.services import position_service
from app.services.errors import NotFoundError
from app.services.position_service import (
    BanqueColonne,
    CompteColonne,
    LigneDevise,
    TableauBanques,
)


def _company(db: Session, company_id: int) -> Company:
    company = account_repository.get_company(db, company_id)
    if company is None or not company.actif:
        raise NotFoundError("Société introuvable.")
    return company


def _date_fin(jour: date | None) -> date:
    """La date demandée (aujourd'hui par défaut), jamais après aujourd'hui."""
    today = position_service.business_today()
    return min(jour or today, today)


def _soldes(
    db: Session, account_ids: list[int], date_fin: date
) -> dict[int, tuple[tuple[date, Decimal], ...]]:
    """Soldes par compte et par jour jusqu'à `date_fin` : la dernière opération du jour l'emporte
    sur le solde du jour (décision du 03/10/2026). Un compte qui a un relevé importé ne lit que son
    relevé : ses soldes saisis sont ignorés, pour que « Disponible Fc reel » soit le solde de
    clôture du relevé (décision du 08/10/2026)."""
    alimentes = position_repository.comptes_alimentes_par_releve(db, account_ids)
    saisies: dict[int, list[tuple[date, Decimal]]] = defaultdict(list)
    for account_id, date_solde, solde in position_repository.soldes_until(
        db, account_ids, date_fin
    ):
        if account_id not in alimentes:
            saisies[account_id].append((date_solde, solde))
    operations: dict[int, list[tuple[date, Decimal]]] = defaultdict(list)
    for account_id, jour, solde in position_repository.last_operation_soldes(
        db, account_ids, date_fin
    ):
        operations[account_id].append((jour, solde))
    # Opérations en cours d'un fichier à part : déjà dans le solde de la banque (20/10/2026)
    en_cours: dict[int, list[tuple[date, date | None, Decimal]]] = defaultdict(list)
    for account_id, debut, fin, montant in position_repository.en_cours_hors_releve(
        db, account_ids, date_fin
    ):
        en_cours[account_id].append((debut, fin, montant))
    return {
        account_id: position_service.avec_en_cours(
            position_service.fusion_soldes(operations[account_id], saisies[account_id]),
            en_cours[account_id],
        )
        for account_id in account_ids
    }


# Soldes retenus par compte et par jour : réutilisés par le dashboard (P15, 14/10/2026)
soldes_par_compte = _soldes


def banques_table(db: Session, company_id: int, jour: date | None) -> TableauBanques:
    """Tableau Banques de la société jusqu'à `jour` (aujourd'hui par défaut, jamais après)."""
    company = _company(db, company_id)
    date_fin = _date_fin(jour)

    # Plusieurs comptes courants MAD par banque possibles (23/10/2026) : la colonne en fait la somme
    par_banque: dict[int, list[BankAccount]] = defaultdict(list)
    for account in sorted(
        position_repository.current_mad_accounts(db, company.id), key=lambda a: a.id
    ):
        par_banque[account.bank_id].append(account)
    soldes = _soldes(db, [a.id for comptes in par_banque.values() for a in comptes], date_fin)

    colonnes = []
    for bank in position_repository.active_banks(db):
        comptes = par_banque.get(bank.id, [])
        taux = {account.taux_interet for account in comptes}
        colonnes.append(
            BanqueColonne(
                bank_id=bank.id,
                code=bank.code,
                logo=bank.logo,
                bank_account_id=comptes[0].id if comptes else None,
                # Un seul taux affiché : celui des comptes s'il est le même pour tous
                taux_interet=taux.pop() if len(taux) == 1 else None,
                ligne=sum((a.credit_autorise for a in comptes), Decimal("0.00"))
                if comptes
                else None,
                soldes=position_service.somme_soldes([soldes[a.id] for a in comptes])
                if comptes
                else (),
                comptes=tuple(
                    CompteColonne(a.numero, soldes[a.id], a.credit_autorise) for a in comptes
                ),
            )
        )
    return position_service.tableau_banques(colonnes, date_fin)


@dataclass(frozen=True)
class TableauDevises:
    date_fin: date
    # Faux pour une société sans compte en devise ni DH convertible (Tefil) : pas de tableau
    affiche: bool
    banques: tuple[Bank, ...]
    lignes: tuple[LigneDevise, ...]


def devises_table(db: Session, company_id: int, jour: date | None) -> TableauDevises:
    """Lignes EUR et USD du tableau Devises : soldes des comptes en devise, sans conversion
    (décision du 05/10/2026). La ligne Exp DH convertible reste saisie à la main."""
    company = _company(db, company_id)
    date_fin = _date_fin(jour)
    devises = position_service.DEVISES_CALCULEES

    banks = tuple(position_repository.active_banks(db))
    accounts = sorted(
        position_repository.currency_accounts(db, company.id, devises), key=lambda a: a.id
    )
    soldes = _soldes(db, [account.id for account in accounts], date_fin)
    lignes = []
    for devise in devises:
        # Plusieurs comptes de la même banque dans cette devise : somme (23/10/2026)
        comptes: dict[int, list[CompteColonne]] = defaultdict(list)
        for account in accounts:
            if account.devise == devise:
                comptes[account.bank_id].append(CompteColonne(account.numero, soldes[account.id]))
        par_banque = {
            bank_id: position_service.somme_soldes([c.soldes for c in liste])
            for bank_id, liste in comptes.items()
        }
        lignes.append(
            position_service.ligne_devise(
                devise, [bank.id for bank in banks], par_banque, date_fin, comptes
            )
        )
    return TableauDevises(
        date_fin=date_fin,
        affiche=position_repository.has_currency_table(db, company.id, devises),
        banques=banks,
        lignes=tuple(lignes),
    )
