"""Données de démonstration pour le développement. Refusées en production.

Tout est marqué « DEMO » / « DÉMO » pour ne jamais être pris pour des données réelles. Les chiffres
viennent de la maquette du dashboard. Les prévisions Escompte, Refinancement et Chèques sont volontairement
absentes : leur sens (entrée ou sortie) n'est pas encore tranché par le métier.
"""

from collections import Counter
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    Bank,
    BankAccount,
    BankAccountBalance,
    CashForecast,
    Company,
    ExchangeRate,
    ForecastCategory,
)
from app.seeds.common import SeedError, get_by_code, get_or_create

D = Decimal
ZERO = D("0")

# Comptes courants MAD de Simtis, un par banque : (banque, solde, crédit autorisé, crédit utilisé, taux)
MAD_ACCOUNTS = [
    ("AWB", D("400000"), D("500000"), D("250000"), D("0.045")),
    ("BMCE", D("200000"), D("300000"), D("150000"), D("0.0475")),
    ("BP", D("650000"), D("600000"), D("200000"), D("0.0425")),
    ("CIH", D("1200000"), D("800000"), D("300000"), D("0.05")),
    ("BMCI", D("300000"), D("400000"), D("100000"), D("0.048")),
]

# Évolution du solde sur les 3 derniers jours (J-2, J-1, J) : alimente les lignes « facilité de caisse »
SOLDE_DELTAS = (D("-30000"), D("-12000"), D("0"))


def ensure_demo_allowed() -> None:
    if get_settings().app_env == "production":
        raise SeedError("Les données de démonstration sont interdites en production (APP_ENV).")


def _account(
    session: Session,
    created: Counter[str],
    *,
    company: Company,
    bank: Bank,
    numero: str,
    devise: str = "MAD",
    type_compte: str = "Courant",
    credit_autorise: Decimal = ZERO,
    taux_interet: Decimal | None = None,
) -> BankAccount:
    account, _ = get_or_create(
        session,
        BankAccount,
        {"numero": numero},
        {
            "company_id": company.id,
            "bank_id": bank.id,
            "libelle": "Compte DÉMO",
            "devise": devise,
            "type_compte": type_compte,
            "compte_comptable": "5141" if devise == "MAD" else None,
            "credit_autorise": credit_autorise,
            "taux_interet": taux_interet,
        },
        created,
    )
    return account


def _balances(
    session: Session,
    created: Counter[str],
    account: BankAccount,
    today: date,
    solde: Decimal,
    credit_utilise: Decimal,
    *,
    days: int = 3,
) -> None:
    for offset in range(days):
        jour = today - timedelta(days=days - 1 - offset)
        get_or_create(
            session,
            BankAccountBalance,
            {"bank_account_id": account.id, "date_solde": jour},
            {
                "solde": solde + SOLDE_DELTAS[offset + len(SOLDE_DELTAS) - days],
                "credit_utilise": credit_utilise,
                "source": "Saisie",
                "commentaire": "DÉMO",
            },
            created,
        )


def seed_demo(session: Session, today: date | None = None) -> Counter[str]:
    """Crée les comptes, soldes, taux de change et prévisions de démonstration manquants.

    Suppose que les seeds de référence ont été chargés. Ne valide pas la transaction.
    """
    ensure_demo_allowed()
    today = today or date.today()
    created: Counter[str] = Counter()

    simtis = get_by_code(session, Company, "SIMTIS")
    societe_x = get_by_code(session, Company, "SOCX")
    banks = {
        code: get_by_code(session, Bank, code) for code in ("AWB", "BMCE", "BP", "CIH", "BMCI")
    }

    for code, solde, credit_autorise, credit_utilise, taux in MAD_ACCOUNTS:
        account = _account(
            session,
            created,
            company=simtis,
            bank=banks[code],
            numero=f"DEMO-{code}-MAD-001",
            credit_autorise=credit_autorise,
            taux_interet=taux,
        )
        _balances(session, created, account, today, solde, credit_utilise)

    # Devises : les montants restent dans leur devise, sans crédit
    eur = _account(
        session, created, company=simtis, bank=banks["CIH"], numero="DEMO-CIH-EUR-001", devise="EUR"
    )
    _balances(session, created, eur, today, D("25000"), D("0"), days=1)
    usd = _account(
        session, created, company=simtis, bank=banks["AWB"], numero="DEMO-AWB-USD-001", devise="USD"
    )
    _balances(session, created, usd, today, D("18000"), D("0"), days=1)
    dh_convertible = _account(
        session,
        created,
        company=simtis,
        bank=banks["BMCE"],
        numero="DEMO-BMCE-DHC-001",
        type_compte="DH convertible",
    )
    _balances(session, created, dh_convertible, today, D("90000"), D("0"), days=1)

    # Seconde société : ses comptes ne sont jamais consolidés avec ceux de Simtis
    socx = _account(
        session,
        created,
        company=societe_x,
        bank=banks["BP"],
        numero="DEMO-BP-SOCX-001",
        credit_autorise=D("200000"),
        taux_interet=D("0.046"),
    )
    _balances(session, created, socx, today, D("150000"), D("50000"))

    for devise, taux in (("EUR", D("10.8")), ("USD", D("9.95"))):
        get_or_create(
            session,
            ExchangeRate,
            {"devise": devise, "date_taux": today},
            {"taux": taux, "source": "DÉMO"},
            created,
        )

    # (catégorie, sens, montant, jour, banque). Sans banque = montant de la journée.
    previsions = [
        ("ENCAISSEMENT", "Entrée", D("450000"), 1, None),
        ("ENCAISSEMENT", "Entrée", D("300000"), 2, "AWB"),
        ("DOUANE", "Sortie", D("80000"), 1, None),
        ("PAIE", "Sortie", D("250000"), 3, None),
    ]
    for code, sens, montant, jours, bank_code in previsions:
        category = get_by_code(session, ForecastCategory, code)
        date_prevue = today + timedelta(days=jours)
        libelle = f"DÉMO {category.libelle} {date_prevue:%d/%m}"
        get_or_create(
            session,
            CashForecast,
            {"company_id": simtis.id, "libelle": libelle},
            {
                "bank_id": banks[bank_code].id if bank_code else None,
                "category_id": category.id,
                "sens": sens,
                "date_prevue": date_prevue,
                "montant": montant,
                "devise": "MAD",
            },
            created,
        )

    return created
