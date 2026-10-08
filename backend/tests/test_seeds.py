"""Les seeds : complets, relançables sans risque, et qui ne touchent jamais à une donnée existante."""

from collections import Counter
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.security import verify_password
from app.models import (
    Bank,
    BankAccount,
    BankAccountBalance,
    CashForecast,
    Company,
    Currency,
    ExchangeRate,
    ForecastCategory,
    Permission,
    PointageType,
    Role,
    User,
)
from app.seeds.__main__ import main
from app.seeds.common import SeedError
from app.seeds.demo import DEMO_PASSWORD, DEMO_USERS, seed_demo
from app.seeds.reference import seed_reference

TODAY = date(2026, 9, 30)

ALL_PERMISSIONS = {
    "banks.manage",
    "statements.import",
    "position.view",
    "accounting.import",
    "reconciliation.view",
    "reconciliation.validate",
    "discrepancies.manage",
    "forecasts.manage",
    "dashboard.view",
    "admin.users",
    "admin.roles",
    "audit.view",
}
CONSULTATION = {"position.view", "reconciliation.view", "dashboard.view"}

# Matrice de la phase P5, écrite ici indépendamment du code : toute dérive fait échouer le test
EXPECTED_ROLES = {
    "ADMIN": ALL_PERMISSIONS,
    "TRESORERIE": CONSULTATION | {"banks.manage", "statements.import", "forecasts.manage"},
    "COMPTABLE": CONSULTATION
    | {"accounting.import", "reconciliation.validate", "discrepancies.manage"},
    "RESPONSABLE": CONSULTATION | {"reconciliation.validate", "discrepancies.manage", "audit.view"},
    "DIRECTION": CONSULTATION,
}


def count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


# --- Données de référence ------------------------------------------------------------------------


def test_reference_seed_creates_the_expected_rows(db):
    created = seed_reference(db)

    assert created == Counter(
        companies=2,
        banks=5,
        currencies=3,
        # Les 74 catégories de pointage sont déjà créées par la migration 0017
        forecast_categories=7,
        permissions=12,
        roles=5,
        reconciliation_rules=9,
    )


def test_reference_seed_can_be_run_again_without_changes(db):
    seed_reference(db)
    before = {
        model: count(db, model)
        for model in (Company, Bank, Currency, Permission, Role, PointageType)
    }

    second = seed_reference(db)

    assert second == Counter()
    assert {model: count(db, model) for model in before} == before


def test_banks_follow_the_workbook_column_order(db):
    seed_reference(db)

    banks = db.scalars(select(Bank).order_by(Bank.ordre_affichage)).all()

    assert [bank.code for bank in banks] == ["AWB", "BMCE", "BP", "CIH", "BMCI"]
    assert banks[0].nom == "Attijariwafa"
    assert all(bank.logo and bank.logo.startswith("/banques/") for bank in banks)


def test_two_companies_are_created(db):
    seed_reference(db)

    companies = {c.code: c.nom for c in db.scalars(select(Company))}

    assert companies == {"SIMTIS": "Simtis", "SOCX": "Tefil"}  # nom confirmé le 05/10/2026


def test_a_renamed_company_keeps_its_name_after_a_new_seed(db):
    seed_reference(db)
    second_company = db.scalar(select(Company).filter_by(code="SOCX"))
    second_company.nom = "Nom définitif"
    db.flush()

    seed_reference(db)
    db.refresh(second_company)

    assert second_company.nom == "Nom définitif"


def test_forecast_categories_only_have_a_default_direction_when_certain(db):
    seed_reference(db)

    directions = {c.code: c.sens_par_defaut for c in db.scalars(select(ForecastCategory))}

    assert directions == {
        "ENCAISSEMENT": "Entrée",
        "DOUANE": "Sortie",
        "PAIE": "Sortie",
        "ESCOMPTE": None,
        "REFINANCEMENT": None,
        "CHEQUES": None,
        "AUTRE": None,
    }


def test_currencies_do_not_include_dh_convertible(db):
    """« Exp DH convertible » est un type de compte en MAD, pas une devise."""
    seed_reference(db)

    assert {c.code for c in db.scalars(select(Currency))} == {"MAD", "EUR", "USD"}


@pytest.mark.parametrize(("role_code", "expected"), EXPECTED_ROLES.items())
def test_role_permissions_follow_the_p5_matrix(db, role_code, expected):
    seed_reference(db)

    role = db.scalar(select(Role).filter_by(code=role_code))

    assert {permission.code for permission in role.permissions} == expected


def test_permission_changes_made_by_an_administrator_are_not_overwritten(db):
    seed_reference(db)
    role = db.scalar(select(Role).filter_by(code="TRESORERIE"))
    forecasts = db.scalar(select(Permission).filter_by(code="forecasts.manage"))
    role.permissions.remove(forecasts)
    db.flush()

    seed_reference(db)
    db.refresh(role)

    assert "forecasts.manage" not in {p.code for p in role.permissions}


# --- Données de démonstration --------------------------------------------------------------------


def test_demo_seed_creates_accounts_balances_rates_and_forecasts(db):
    seed_reference(db)

    created = seed_demo(db, today=TODAY)

    assert created == Counter(
        bank_accounts=9, bank_account_balances=21, exchange_rates=2, cash_forecasts=4, users=5
    )


def test_demo_seed_can_be_run_again_without_changes(db):
    seed_reference(db)
    seed_demo(db, today=TODAY)

    assert seed_demo(db, today=TODAY) == Counter()
    assert count(db, BankAccount) == 9


def test_demo_data_is_always_marked_as_demo(db):
    seed_reference(db)
    seed_demo(db, today=TODAY)

    assert all(
        a.numero.startswith("DEMO-") and "DÉMO" in a.libelle
        for a in db.scalars(select(BankAccount))
    )
    assert all(f.libelle.startswith("DÉMO") for f in db.scalars(select(CashForecast)))
    assert all(r.source == "DÉMO" for r in db.scalars(select(ExchangeRate)))


def test_demo_gives_each_bank_three_days_of_balances(db):
    """Alimente les 3 lignes « facilité de caisse » du tableau Banques."""
    seed_reference(db)
    seed_demo(db, today=TODAY)
    cih = db.scalar(select(BankAccount).filter_by(numero="DEMO-CIH-MAD-001"))

    balances = db.scalars(
        select(BankAccountBalance)
        .filter_by(bank_account_id=cih.id)
        .order_by(BankAccountBalance.date_solde)
    ).all()

    assert [b.date_solde for b in balances] == [
        date(2026, 9, 28),
        date(2026, 9, 29),
        date(2026, 9, 30),
    ]
    assert [b.solde for b in balances] == [
        Decimal("1170000"),
        Decimal("1188000"),
        Decimal("1200000"),
    ]
    assert cih.credit_autorise == Decimal("800000")
    assert cih.taux_interet == Decimal("0.05")


def test_demo_second_company_accounts_are_separate(db):
    seed_reference(db)
    seed_demo(db, today=TODAY)

    per_company = Counter(a.company.code for a in db.scalars(select(BankAccount)))

    assert per_company == Counter(SIMTIS=8, SOCX=1)


def test_demo_has_a_dh_convertible_account_in_mad(db):
    seed_reference(db)
    seed_demo(db, today=TODAY)

    account = db.scalar(select(BankAccount).filter_by(type_compte="DH convertible"))

    assert account.devise == "MAD"


def test_demo_omits_forecast_categories_whose_direction_is_undecided(db):
    seed_reference(db)
    seed_demo(db, today=TODAY)

    used = {f.category.code for f in db.scalars(select(CashForecast))}

    assert used == {"ENCAISSEMENT", "DOUANE", "PAIE"}


def test_demo_seed_needs_the_reference_data(db):
    with pytest.raises(SeedError, match="python -m app.seeds"):
        seed_demo(db, today=TODAY)


def test_demo_seed_is_refused_in_production(db, production_env):
    seed_reference(db)

    with pytest.raises(SeedError, match="interdites en production"):
        seed_demo(db, today=TODAY)

    assert count(db, BankAccount) == 0


def test_command_line_refuses_demo_in_production_before_writing(production_env, capsys):
    assert main(["--demo"]) == 1

    assert "interdites en production" in capsys.readouterr().err


def test_demo_creates_one_user_per_role_with_a_working_password(db):
    seed_reference(db)
    seed_demo(db, today=TODAY)

    users = {user.email: user for user in db.scalars(select(User))}

    assert set(users) == {email for email, _, _ in DEMO_USERS}
    for email, nom, role_code in DEMO_USERS:
        user = users[email]
        assert user.nom == nom
        assert [role.code for role in user.roles] == [role_code]
        assert verify_password(DEMO_PASSWORD, user.mot_de_passe_hash)
        assert DEMO_PASSWORD not in user.mot_de_passe_hash


def test_demo_users_are_never_created_in_production(db, production_env):
    seed_reference(db)

    with pytest.raises(SeedError):
        seed_demo(db, today=TODAY)

    assert count(db, User) == 0
