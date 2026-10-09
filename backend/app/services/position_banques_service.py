"""Tableaux Banques (P8.1) et Devises (soldes EUR / USD) : lit la base et applique les règles pures
de `position_service`."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Bank, Company
from app.repositories import account_repository, position_repository
from app.services import position_service
from app.services.errors import NotFoundError
from app.services.position_service import BanqueColonne, LigneDevise, TableauBanques


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
    return {
        account_id: position_service.fusion_soldes(operations[account_id], saisies[account_id])
        for account_id in account_ids
    }


def banques_table(db: Session, company_id: int, jour: date | None) -> TableauBanques:
    """Tableau Banques de la société jusqu'à `jour` (aujourd'hui par défaut, jamais après)."""
    company = _company(db, company_id)
    date_fin = _date_fin(jour)

    accounts = {
        account.bank_id: account
        for account in position_repository.current_mad_accounts(db, company.id)
    }
    soldes = _soldes(db, [account.id for account in accounts.values()], date_fin)

    colonnes = []
    for bank in position_repository.active_banks(db):
        account = accounts.get(bank.id)
        colonnes.append(
            BanqueColonne(
                bank_id=bank.id,
                code=bank.code,
                logo=bank.logo,
                bank_account_id=account.id if account else None,
                taux_interet=account.taux_interet if account else None,
                ligne=account.credit_autorise if account else None,
                soldes=soldes[account.id] if account else (),
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
    accounts = position_repository.currency_accounts(db, company.id, devises)
    soldes = _soldes(db, [account.id for account in accounts], date_fin)
    lignes = []
    for devise in devises:
        par_banque = {
            account.bank_id: soldes[account.id] for account in accounts if account.devise == devise
        }
        lignes.append(
            position_service.ligne_devise(devise, [bank.id for bank in banks], par_banque, date_fin)
        )
    return TableauDevises(
        date_fin=date_fin,
        affiche=position_repository.has_currency_table(db, company.id, devises),
        banques=banks,
        lignes=tuple(lignes),
    )
