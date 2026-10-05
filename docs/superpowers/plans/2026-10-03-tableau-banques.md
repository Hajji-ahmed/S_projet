# Tableau Banques calculé (P8.1) — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** calculer et afficher le tableau Banques du classeur (Taux, LIGNE, une ligne « facilité de caisse » par jour, Disponible Fc reel, TOTAL, DEPASSEMENT) à partir des soldes du jour déjà enregistrés.

**Architecture :** calcul à la demande, sans nouvelle table. Les règles sont des fonctions pures en `Decimal` dans `position_service.py`. Un petit service d'orchestration lit la base par un repository dédié et appelle ces fonctions. Un endpoint mince `GET /api/position/banques` renvoie le tableau. Côté frontend, un composant en lecture seule `BanquesTable` est placé en tête de `/position-bancaire`.

**Tech Stack :** FastAPI, SQLAlchemy 2, Pydantic v2, pytest (base `simtis_test`), Next.js 16, TypeScript, Tailwind v4 (tokens `simtis-*`), Vitest, Edge via playwright-core.

**Spec :** `docs/superpowers/specs/2026-10-03-tableau-banques-design.md`

## Global Constraints

- Langue : français pour l'interface, les messages d'erreur, les commentaires et la documentation. Libellés exacts du classeur : « Banque », « Taux », « LIGNE », « facilité de caisse », « Disponible Fc reel », « TOTAL », « DEPASSEMENT ».
- Argent : `Decimal` côté serveur, chaînes exactes dans l'API (`"300000.00"`), jamais de `float`. Le frontend ne calcule ni TOTAL ni DEPASSEMENT, et ne convertit aucun montant pour décider d'une couleur (le signe se lit sur la chaîne).
- Une valeur inconnue reste `null` / « - », jamais 0.
- Couches : `api/` mince → `services/` → `repositories/` → `models/`. Erreurs métier par `NotFoundError` (404) avec un message en français.
- Sécurité : routeur `position` déjà dans `protected_router` ; permission `position.view`.
- Interface : tokens `simtis-*` uniquement, icônes Lucide, aucun emoji, logos par `BankLabel` (empilés dans les en-têtes), montants par `formatAmount()`.
- Ne jamais écrire de test dont le résultat dépend du décalage horaire du Maroc en 2026 : dates de test en 2025, ou comparées à `business_today()` du même processus.
- **Aucun commit** : l'utilisateur commite lui-même. Les étapes « Commit » du modèle sont remplacées par « Ne pas commiter ».
- Avant de déclarer le travail fini, toutes ces commandes passent : `docker compose run --rm backend ruff check .`, `docker compose run --rm backend ruff format --check .`, `docker compose run --rm backend pytest`, `docker compose run --rm backend alembic check`, et dans `frontend/` : `npm run lint && npm run format:check && npm run typecheck && npm test && npm run build`.
- Contrôle Edge en lecture seule : il n'écrit rien dans la base de développement (elle contient les imports réels de l'utilisateur).

## Review Focus

1. Ancien compte courant MAD **désactivé** de la même banque, avec des soldes : il doit être ignoré, seul le compte actif compte. Test : `test_only_the_active_mad_current_account_counts` (tâche 2).
2. Date demandée **avant le premier solde** : aucune ligne facilité de caisse, Disponible Fc reel tout en « - », pas d'erreur. Test : `test_date_before_the_first_balance_gives_no_day` (tâche 2).
3. Société **désactivée** : 404 comme une société inconnue, et non un tableau vide. Test : `test_unknown_or_inactive_company_gives_404` (tâche 2).
4. **Long historique** (plus d'un an de jours calendaires) : toutes les lignes, sans trou, en un appel. Test : `test_long_history_has_one_row_per_calendar_day` (tâche 1).
5. Taux **absent** sur un compte : « - » et non « 0,00 % ». Tests : `formatTaux(null)` (tâche 3) et `taux_pct` à `null` dans `test_validated_example_through_the_api` (tâche 2).

---

## Structure des fichiers

| Fichier | Rôle |
|---|---|
| `backend/app/services/position_service.py` (modifier) | Fonctions pures : `disponible_fc_reel`, `depassement`, `tableau_banques` et leurs dataclasses |
| `backend/app/repositories/position_repository.py` (créer) | Lectures : banques actives, comptes courants MAD actifs d'une société, soldes non nuls jusqu'à une date |
| `backend/app/services/position_banques_service.py` (créer) | Orchestration : contrôle de la société, date de fin, assemblage des colonnes, appel du calcul |
| `backend/app/schemas/position.py` (créer) | `BanquesTableOut` et ses sous-schémas |
| `backend/app/api/position.py` (modifier) | `GET /position/banques` |
| `backend/tests/test_position_service.py` (modifier) | Tests des fonctions pures |
| `backend/tests/test_position_banques_api.py` (créer) | Tests de l'API |
| `frontend/types/position.ts` (créer) | Types de la réponse |
| `frontend/services/position.ts` (créer) | `getBanquesTable` |
| `frontend/lib/position.ts` + `position.test.ts` (créer) | `JOURS_AFFICHES`, `formatTaux`, `formatJour`, `signTone` |
| `frontend/components/position/BanquesTable.tsx` (créer) | Carte « Banques » |
| `frontend/components/position/PositionView.tsx` (modifier) | Place la carte en premier, nouvelle description |
| `CLAUDE.md`, `docs/specs/Plan_Phases_Realisation_SIMTIS.md`, `.claude/skills/simtis-design/pages.md` (modifier) | Documentation |

Note de conception : la spécification place la construction du tableau dans `position_service`. Les **règles** y sont, en fonctions pures. La **lecture de la base** va dans `position_banques_service.py`, parce que la docstring de `position_service` garantit qu'il n'accède pas à la base. Le comportement reste celui de la spécification.

---

### Task 1 : calculs purs du tableau Banques

**Files :**
- Modify : `backend/app/services/position_service.py` (ajout en fin de fichier, et import `timedelta` / `Sequence`)
- Test : `backend/tests/test_position_service.py`

**Interfaces :**
- Consumes : rien.
- Produces :
  - `disponible_fc_reel(solde: Decimal, ligne: Decimal) -> Decimal`
  - `depassement(total: Decimal | None, total_lignes: Decimal) -> Decimal | None`
  - `@dataclass(frozen=True) BanqueColonne(bank_id: int, code: str, logo: str | None, bank_account_id: int | None, taux_interet: Decimal | None, ligne: Decimal | None, soldes: tuple[tuple[date, Decimal], ...])`
  - `@dataclass(frozen=True) Cellule(bank_id: int, valeur: Decimal | None, date_solde: date | None, reprise: bool)`
  - `@dataclass(frozen=True) LigneTableau(cellules: tuple[Cellule, ...], total: Decimal | None, depassement: Decimal | None)`
  - `@dataclass(frozen=True) JourTableau(date: date, ligne: LigneTableau)`
  - `@dataclass(frozen=True) TableauBanques(date_fin: date, banques: tuple[BanqueColonne, ...], ligne_total: Decimal | None, jours: tuple[JourTableau, ...], disponible: LigneTableau)`
  - `tableau_banques(banques: Sequence[BanqueColonne], date_fin: date) -> TableauBanques`

- [ ] **Step 1 : écrire les tests qui échouent**

Ajouter à la fin de `backend/tests/test_position_service.py`, et compléter l'import du haut :

```python
from datetime import date, timedelta

from app.services.position_service import (
    BanqueColonne,
    Cellule,
    LatestValues,
    account_figures,
    credit_disponible,
    depassement,
    disponible_fc_reel,
    latest_values,
    position_disponible,
    tableau_banques,
)
```

```python
# --- Tableau Banques (P8.1) ------------------------------------------------------------------------

# Dates passées : aucun résultat ne dépend de la date du jour
J26, J27, J28, J29, J30 = (date(2025, 9, d) for d in (26, 27, 28, 29, 30))


def colonne(bank_id, ligne="0", soldes=(), *, compte=True, taux=None) -> BanqueColonne:
    return BanqueColonne(
        bank_id=bank_id,
        code=f"B{bank_id}",
        logo=None,
        bank_account_id=100 + bank_id if compte else None,
        taux_interet=D(taux) if taux else None,
        ligne=D(ligne) if compte else None,
        soldes=tuple((jour, D(solde)) for jour, solde in soldes),
    )


def test_facilite_de_caisse_is_balance_plus_ligne():
    assert disponible_fc_reel(D("-200000"), D("500000")) == D("300000")


def test_depassement_is_total_minus_lignes_and_unknown_without_total():
    assert depassement(D("700000"), D("800000")) == D("-100000")
    assert depassement(None, D("800000")) is None


def test_validated_example():
    """Décision du 02/10/2026 : 300 000 + 400 000 = 700 000 ; 700 000 − 800 000 = −100 000."""
    awb = colonne(1, "500000", [(J30, "-200000")])
    bmce = colonne(2, "300000", [(J30, "100000")])

    table = tableau_banques([awb, bmce], J30)

    [jour] = table.jours
    assert jour.date == J30
    assert jour.ligne.cellules == (
        Cellule(1, D("300000"), J30, False),
        Cellule(2, D("400000"), J30, False),
    )
    assert jour.ligne.total == D("700000")
    assert jour.ligne.depassement == D("-100000")
    assert table.ligne_total == D("800000")
    assert table.disponible == jour.ligne
    assert table.date_fin == J30


def test_a_day_without_balance_reuses_the_last_known_one():
    awb = colonne(1, "100", [(J28, "10"), (J30, "30")])
    bmce = colonne(2, "200", [(J28, "20")])

    table = tableau_banques([awb, bmce], J30)

    j28, j29, j30 = table.jours
    assert j29.ligne.cellules == (Cellule(1, D("110"), J28, True), Cellule(2, D("220"), J28, True))
    assert j30.ligne.cellules == (Cellule(1, D("130"), J30, False), Cellule(2, D("220"), J28, True))
    assert j30.ligne.total == D("350")
    assert j30.ligne.depassement == D("50")


def test_bank_before_its_first_balance_is_left_out_of_both_totals():
    awb = colonne(1, "100", [(J28, "10")])
    bmce = colonne(2, "200", [(J29, "20")])

    j28, j29 = tableau_banques([awb, bmce], J29).jours

    assert j28.ligne.cellules[1] == Cellule(2, None, None, False)
    assert j28.ligne.total == D("110")
    assert j28.ligne.depassement == D("10")  # 110 − 100 : la LIGNE de BMCE n'est pas comptée
    assert j29.ligne.total == D("330")


def test_every_calendar_day_has_a_row_weekends_included():
    awb = colonne(1, "0", [(J26, "1"), (J29, "4")])  # vendredi puis lundi

    table = tableau_banques([awb], J29)

    assert [jour.date for jour in table.jours] == [J26, J27, J28, J29]


def test_balances_after_the_end_date_are_ignored():
    awb = colonne(1, "0", [(J29, "1"), (date(2025, 10, 1), "999")])

    table = tableau_banques([awb], J30)

    assert [jour.date for jour in table.jours] == [J29, J30]
    assert table.disponible.cellules[0] == Cellule(1, D("1"), J29, True)


def test_bank_without_account_has_empty_cells_and_no_ligne():
    awb = colonne(1, "100", [(J30, "1")])
    bp = colonne(3, compte=False)

    table = tableau_banques([awb, bp], J30)

    assert table.jours[0].ligne.cellules[1] == Cellule(3, None, None, False)
    assert table.ligne_total == D("100")


def test_no_balance_at_all_gives_no_day_and_unknown_disponible():
    table = tableau_banques([colonne(1, "100"), colonne(2, compte=False)], J30)

    assert table.jours == ()
    assert table.disponible.total is None
    assert table.disponible.depassement is None
    assert [cellule.valeur for cellule in table.disponible.cellules] == [None, None]
    assert table.ligne_total == D("100")


def test_no_account_at_all_gives_no_ligne_total():
    assert tableau_banques([colonne(1, compte=False)], J30).ligne_total is None


def test_long_history_has_one_row_per_calendar_day():
    debut = date(2024, 9, 1)
    awb = colonne(1, "0", [(debut, "5")])

    table = tableau_banques([awb], debut + timedelta(days=399))

    assert len(table.jours) == 400
    assert table.jours[-1].ligne.cellules[0].reprise is True


def test_table_amounts_are_decimals():
    table = tableau_banques([colonne(1, "500000.50", [(J30, "0.25")])], J30)

    line = table.jours[0].ligne
    assert isinstance(line.cellules[0].valeur, Decimal)
    assert isinstance(line.total, Decimal)
    assert line.cellules[0].valeur == D("500000.75")
```

- [ ] **Step 2 : lancer les tests et constater l'échec**

Run : `docker compose run --rm backend pytest tests/test_position_service.py -q`
Expected : erreur à la collecte, `ImportError: cannot import name 'BanqueColonne'`.

- [ ] **Step 3 : écrire le code**

Dans `backend/app/services/position_service.py`, compléter la docstring et les imports :

```python
"""Calculs de position (CDC §5.2). Fonctions pures, en `Decimal`, sans accès à la base.

    Crédit disponible   = Crédit autorisé (LIGNE) − Crédit utilisé
    Position disponible = Solde bancaire + Crédit disponible
    Disponible FC réel  = Solde bancaire + LIGNE (aussi la « facilité de caisse » d'un jour)
    DEPASSEMENT         = TOTAL de la ligne − somme des LIGNES des mêmes banques

Une valeur inconnue (jamais saisie) reste inconnue (`None`) : elle n'est jamais remplacée par zéro.
Réutilisé par la position bancaire (P8).
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
```

Puis ajouter en fin de fichier :

```python
# --- Tableau Banques (P8.1, décisions du 02/10/2026) -----------------------------------------------


@dataclass(frozen=True)
class BanqueColonne:
    """Une colonne du tableau : une banque active et son compte courant MAD actif, s'il existe.

    `ligne` et `bank_account_id` sont `None` sans compte ; `soldes` = (date, solde) non nuls.
    """

    bank_id: int
    code: str
    logo: str | None
    bank_account_id: int | None
    taux_interet: Decimal | None
    ligne: Decimal | None
    soldes: tuple[tuple[date, Decimal], ...]


@dataclass(frozen=True)
class Cellule:
    bank_id: int
    valeur: Decimal | None
    # Date du solde utilisé ; `reprise` quand ce n'est pas le jour de la ligne
    date_solde: date | None
    reprise: bool


@dataclass(frozen=True)
class LigneTableau:
    cellules: tuple[Cellule, ...]
    total: Decimal | None
    depassement: Decimal | None


@dataclass(frozen=True)
class JourTableau:
    date: date
    ligne: LigneTableau


@dataclass(frozen=True)
class TableauBanques:
    date_fin: date
    banques: tuple[BanqueColonne, ...]
    ligne_total: Decimal | None
    jours: tuple[JourTableau, ...]
    disponible: LigneTableau


def disponible_fc_reel(solde: Decimal, ligne: Decimal) -> Decimal:
    return solde + ligne


def depassement(total: Decimal | None, total_lignes: Decimal) -> Decimal | None:
    return None if total is None else total - total_lignes


def _ligne(
    banques: Sequence[BanqueColonne], jour: date, retenus: dict[int, tuple[date, Decimal]]
) -> LigneTableau:
    """Une ligne du tableau : chaque banque avec son solde retenu, TOTAL et DEPASSEMENT.

    Une banque sans solde retenu (pas de compte, ou avant son premier solde) n'entre ni dans le
    TOTAL ni dans la somme des LIGNES.
    """
    cellules: list[Cellule] = []
    total: Decimal | None = None
    lignes = Decimal("0")
    for banque in banques:
        retenu = retenus.get(banque.bank_id)
        if retenu is None or banque.ligne is None:
            cellules.append(Cellule(banque.bank_id, None, None, False))
            continue
        date_solde, solde = retenu
        valeur = disponible_fc_reel(solde, banque.ligne)
        cellules.append(Cellule(banque.bank_id, valeur, date_solde, date_solde != jour))
        total = valeur if total is None else total + valeur
        lignes += banque.ligne
    return LigneTableau(tuple(cellules), total, depassement(total, lignes))


def tableau_banques(banques: Sequence[BanqueColonne], date_fin: date) -> TableauBanques:
    """Tableau Banques jusqu'à `date_fin` incluse : une ligne par jour calendaire depuis le premier
    solde connu ; un jour sans solde reprend le dernier solde connu de la banque."""
    soldes = {
        banque.bank_id: {jour: solde for jour, solde in banque.soldes if jour <= date_fin}
        for banque in banques
        if banque.bank_account_id is not None
    }
    dates = [jour for par_jour in soldes.values() for jour in par_jour]

    retenus: dict[int, tuple[date, Decimal]] = {}
    jours: list[JourTableau] = []
    if dates:
        jour = min(dates)
        while jour <= date_fin:
            for bank_id, par_jour in soldes.items():
                if jour in par_jour:
                    retenus[bank_id] = (jour, par_jour[jour])
            jours.append(JourTableau(jour, _ligne(banques, jour, retenus)))
            jour += timedelta(days=1)

    lignes = [banque.ligne for banque in banques if banque.ligne is not None]
    return TableauBanques(
        date_fin=date_fin,
        banques=tuple(banques),
        ligne_total=sum(lignes, Decimal("0")) if lignes else None,
        jours=tuple(jours),
        # Disponible Fc reel = la ligne de la date de fin (dernier solde connu + LIGNE)
        disponible=jours[-1].ligne if jours else _ligne(banques, date_fin, {}),
    )
```

- [ ] **Step 4 : lancer les tests et constater le succès**

Run : `docker compose run --rm backend pytest tests/test_position_service.py -q`
Expected : tous les tests passent (les 10 tests existants et les 12 nouveaux).

- [ ] **Step 5 : contrôle du style**

Run : `docker compose run --rm backend ruff check . && docker compose run --rm backend ruff format --check .`
Expected : `All checks passed!`, puis aucun fichier à reformater. Sinon, `ruff format .` puis relancer.

- [ ] **Step 6 : ne pas commiter** (l'utilisateur commite lui-même).

---

### Task 2 : repository, service, schéma et endpoint `GET /api/position/banques`

**Files :**
- Create : `backend/app/repositories/position_repository.py`
- Create : `backend/app/services/position_banques_service.py`
- Create : `backend/app/schemas/position.py`
- Modify : `backend/app/api/position.py`
- Test : `backend/tests/test_position_banques_api.py`

**Interfaces :**
- Consumes (tâche 1) : `BanqueColonne`, `TableauBanques`, `LigneTableau`, `tableau_banques(banques, date_fin)`, `business_today()`.
- Produces :
  - `position_repository.active_banks(db) -> list[Bank]`
  - `position_repository.current_mad_accounts(db, company_id: int) -> list[BankAccount]`
  - `position_repository.soldes_until(db, account_ids: list[int], date_fin: date) -> list[tuple[int, date, Decimal]]`
  - `position_banques_service.banques_table(db, company_id: int, jour: date | None) -> TableauBanques`
  - `schemas.position.BanquesTableOut.from_table(company_id: int, table: TableauBanques) -> BanquesTableOut`
  - Réponse JSON : `{company_id, date_fin, banques: [{bank_id, code, logo, bank_account_id, taux_pct, ligne}], ligne_total, jours: [{date, cellules: [{bank_id, valeur, date_solde, reprise}], total, depassement}], disponible: {cellules, total, depassement}}`

- [ ] **Step 1 : écrire les tests qui échouent**

Créer `backend/tests/test_position_banques_api.py` :

```python
"""Tableau Banques calculé (P8.1) : GET /api/position/banques."""

from datetime import date, timedelta
from decimal import Decimal
from itertools import count

import pytest
from sqlalchemy import select

from app.models import Bank, BankAccount, BankAccountBalance, Company
from app.services.position_service import business_today
from tests.helpers import bearer, build_account, login, make_auth_user, save

URL = "/api/position/banques"
# Dates passées : aucun résultat ne dépend du décalage horaire du Maroc
J28, J29, J30 = date(2025, 9, 28), date(2025, 9, 29), date(2025, 9, 30)
_numeros = count(1)


@pytest.fixture
def direction(client, reference) -> dict[str, str]:
    make_auth_user(reference, "DIRECTION", email="direction@example.com")
    return bearer(login(client, "direction@example.com"))


def company(db, code: str = "SIMTIS") -> Company:
    return db.scalar(select(Company).filter_by(code=code))


def bank(db, code: str) -> Bank:
    return db.scalar(select(Bank).filter_by(code=code))


def account(db, bank_code: str, company_code: str = "SIMTIS", **over) -> BankAccount:
    over.setdefault("numero", f"RIB-POS-{next(_numeros):06d}")
    over.setdefault("type_compte", "Courant")
    return save(db, build_account(company(db, company_code), bank(db, bank_code), **over))


def balance(db, compte: BankAccount, jour: date, solde=None, credit_utilise=None) -> None:
    save(
        db,
        BankAccountBalance(
            bank_account_id=compte.id,
            date_solde=jour,
            solde=None if solde is None else Decimal(solde),
            credit_utilise=None if credit_utilise is None else Decimal(credit_utilise),
        ),
    )


def get(client, headers, db, jour: date | None = J30, code: str = "SIMTIS"):
    params = {"company_id": str(company(db, code).id)}
    if jour is not None:
        params["date"] = jour.isoformat()
    return client.get(URL, params=params, headers=headers)


def cell(body: dict, line: dict, code: str) -> dict:
    index = [banque["code"] for banque in body["banques"]].index(code)
    return line["cellules"][index]


def test_validated_example_through_the_api(client, direction, db):
    awb = account(db, "AWB", credit_autorise=Decimal("500000"), taux_interet=Decimal("0.055"))
    bmce = account(db, "BMCE", credit_autorise=Decimal("300000"))
    balance(db, awb, J30, "-200000")
    balance(db, bmce, J30, "100000")

    response = get(client, direction, db)

    assert response.status_code == 200
    body = response.json()
    assert body["company_id"] == company(db).id
    assert body["date_fin"] == "2025-09-30"
    assert [banque["code"] for banque in body["banques"]] == ["AWB", "BMCE", "BP", "CIH", "BMCI"]
    assert body["banques"][0] == {
        "bank_id": bank(db, "AWB").id,
        "code": "AWB",
        "logo": "/banques/attijariwafa.png",
        "bank_account_id": awb.id,
        "taux_pct": "5.5",
        "ligne": "500000.00",
    }
    assert body["banques"][1]["taux_pct"] is None
    assert body["banques"][2] | {"bank_id": 0} == {
        "bank_id": 0,
        "code": "BP",
        "logo": "/banques/bp.png",
        "bank_account_id": None,
        "taux_pct": None,
        "ligne": None,
    }
    assert body["ligne_total"] == "800000.00"
    [jour] = body["jours"]
    assert jour["date"] == "2025-09-30"
    assert cell(body, jour, "AWB") == {
        "bank_id": bank(db, "AWB").id,
        "valeur": "300000.00",
        "date_solde": "2025-09-30",
        "reprise": False,
    }
    assert cell(body, jour, "BMCE")["valeur"] == "400000.00"
    assert cell(body, jour, "BP")["valeur"] is None
    assert jour["total"] == "700000.00"
    assert jour["depassement"] == "-100000.00"
    assert body["disponible"] == {key: value for key, value in jour.items() if key != "date"}


def test_only_the_active_mad_current_account_counts(client, direction, db):
    courant = account(db, "AWB")
    balance(db, courant, J30, "1000")
    for other in (
        account(db, "AWB", type_compte="DH convertible"),
        account(db, "AWB", devise="EUR"),
        account(db, "AWB", actif=False),  # ancien compte courant MAD désactivé
    ):
        balance(db, other, J30, "999999")

    body = get(client, direction, db).json()

    assert body["banques"][0]["bank_account_id"] == courant.id
    assert cell(body, body["jours"][0], "AWB")["valeur"] == "1000.00"
    assert body["jours"][0]["total"] == "1000.00"


def test_other_company_is_excluded(client, direction, db):
    balance(db, account(db, "AWB", company_code="SOCX"), J30, "5000")

    body = get(client, direction, db).json()

    assert body["banques"][0]["bank_account_id"] is None
    assert body["jours"] == []


def test_inactive_bank_has_no_column(client, direction, db):
    bank(db, "BMCE").actif = False
    db.flush()

    body = get(client, direction, db).json()

    assert [banque["code"] for banque in body["banques"]] == ["AWB", "BP", "CIH", "BMCI"]


def test_balance_row_without_solde_does_not_count(client, direction, db):
    awb = account(db, "AWB")
    balance(db, awb, J28, "1000")
    balance(db, awb, J29, credit_utilise="50")  # crédit utilisé seul

    body = get(client, direction, db, J29).json()

    assert cell(body, body["jours"][-1], "AWB") | {"bank_id": 0} == {
        "bank_id": 0,
        "valeur": "1000.00",
        "date_solde": "2025-09-28",
        "reprise": True,
    }


def test_end_date_is_capped_at_today(client, direction, db):
    balance(db, account(db, "AWB"), J30, "1")
    today = business_today()

    body = get(client, direction, db, today + timedelta(days=30)).json()

    assert body["date_fin"] == today.isoformat()
    assert body["jours"][-1]["date"] == today.isoformat()
    assert len(body["jours"]) == (today - J30).days + 1


def test_default_date_is_today(client, direction, db):
    body = get(client, direction, db, None).json()

    assert body["date_fin"] == business_today().isoformat()


def test_date_before_the_first_balance_gives_no_day(client, direction, db):
    balance(db, account(db, "AWB", credit_autorise=Decimal("100")), J30, "1")

    body = get(client, direction, db, J28).json()

    assert body["jours"] == []
    assert body["disponible"]["total"] is None
    assert body["disponible"]["depassement"] is None
    assert cell(body, body["disponible"], "AWB")["valeur"] is None
    assert body["ligne_total"] == "100.00"


def test_unknown_or_inactive_company_gives_404(client, direction, db):
    unknown = client.get(URL, params={"company_id": "999999"}, headers=direction)
    company(db, "SOCX").actif = False
    db.flush()
    inactive = get(client, direction, db, code="SOCX")

    for response in (unknown, inactive):
        assert response.status_code == 404
        assert response.json() == {"detail": "Société introuvable."}


def test_invalid_date_gives_422(client, direction, db):
    response = client.get(
        URL, params={"company_id": str(company(db).id), "date": "2025-02-30"}, headers=direction
    )

    assert response.status_code == 422


def test_requires_a_token(client, reference):
    assert client.get(URL, params={"company_id": "1"}).status_code == 401


def test_requires_position_view(client, reference, db):
    make_auth_user(reference, email="sans-role@example.com")
    headers = bearer(login(client, "sans-role@example.com"))

    assert get(client, headers, db).status_code == 403
```

- [ ] **Step 2 : lancer les tests et constater l'échec**

Run : `docker compose run --rm backend pytest tests/test_position_banques_api.py -q`
Expected : les tests qui interrogent la route échouent avec `assert 404 == 200` (route inconnue). `test_requires_a_token` peut déjà passer (401 avant la route), ce qui est normal.

- [ ] **Step 3 : repository**

Créer `backend/app/repositories/position_repository.py` :

```python
"""Lectures du tableau Banques (P8.1)."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Bank, BankAccount, BankAccountBalance


def active_banks(db: Session) -> list[Bank]:
    """Banques actives, dans l'ordre des colonnes des tableaux."""
    query = select(Bank).where(Bank.actif.is_(True)).order_by(Bank.ordre_affichage, Bank.code)
    return list(db.scalars(query))


def current_mad_accounts(db: Session, company_id: int) -> list[BankAccount]:
    """Comptes courants MAD actifs de la société : au plus un par banque (index unique partiel)."""
    query = select(BankAccount).where(
        BankAccount.company_id == company_id,
        BankAccount.type_compte == "Courant",
        BankAccount.devise == "MAD",
        BankAccount.actif.is_(True),
    )
    return list(db.scalars(query))


def soldes_until(
    db: Session, account_ids: list[int], date_fin: date
) -> list[tuple[int, date, Decimal]]:
    """(compte, date, solde) des soldes renseignés jusqu'à `date_fin` incluse.

    Une ligne qui ne porte qu'un crédit utilisé (solde vide) n'est pas un solde.
    """
    if not account_ids:
        return []
    query = select(
        BankAccountBalance.bank_account_id, BankAccountBalance.date_solde, BankAccountBalance.solde
    ).where(
        BankAccountBalance.bank_account_id.in_(account_ids),
        BankAccountBalance.date_solde <= date_fin,
        BankAccountBalance.solde.is_not(None),
    )
    return [(row[0], row[1], row[2]) for row in db.execute(query)]
```

- [ ] **Step 4 : service**

Créer `backend/app/services/position_banques_service.py` :

```python
"""Tableau Banques (P8.1) : lit la base et applique les règles pures de `position_service`."""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.repositories import account_repository, position_repository
from app.services import position_service
from app.services.errors import NotFoundError
from app.services.position_service import BanqueColonne, TableauBanques


def banques_table(db: Session, company_id: int, jour: date | None) -> TableauBanques:
    """Tableau Banques de la société jusqu'à `jour` (aujourd'hui par défaut, jamais après)."""
    company = account_repository.get_company(db, company_id)
    if company is None or not company.actif:
        raise NotFoundError("Société introuvable.")

    today = position_service.business_today()
    date_fin = min(jour or today, today)

    accounts = {
        account.bank_id: account
        for account in position_repository.current_mad_accounts(db, company.id)
    }
    soldes: dict[int, list[tuple[date, Decimal]]] = defaultdict(list)
    for account_id, date_solde, solde in position_repository.soldes_until(
        db, [account.id for account in accounts.values()], date_fin
    ):
        soldes[account_id].append((date_solde, solde))

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
                soldes=tuple(soldes[account.id]) if account else (),
            )
        )
    return position_service.tableau_banques(colonnes, date_fin)
```

- [ ] **Step 5 : schéma**

Créer `backend/app/schemas/position.py` :

```python
"""Tableau Banques calculé (P8.1). Montants et taux en texte exact ; inconnu = `null`, jamais 0."""

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel

from app.services.account_service import fraction_to_pct
from app.services.position_service import BanqueColonne, LigneTableau, TableauBanques


class BanqueColonneOut(BaseModel):
    bank_id: int
    code: str
    logo: str | None
    bank_account_id: int | None
    taux_pct: Decimal | None
    ligne: Decimal | None

    @classmethod
    def from_colonne(cls, colonne: BanqueColonne) -> "BanqueColonneOut":
        return cls(
            bank_id=colonne.bank_id,
            code=colonne.code,
            logo=colonne.logo,
            bank_account_id=colonne.bank_account_id,
            taux_pct=fraction_to_pct(colonne.taux_interet),
            ligne=colonne.ligne,
        )


class CelluleOut(BaseModel):
    bank_id: int
    valeur: Decimal | None
    date_solde: dt.date | None
    reprise: bool


class LigneOut(BaseModel):
    cellules: list[CelluleOut]
    total: Decimal | None
    depassement: Decimal | None

    @classmethod
    def from_ligne(cls, ligne: LigneTableau, **extra) -> "LigneOut":
        return cls(
            cellules=[
                CelluleOut(
                    bank_id=c.bank_id, valeur=c.valeur, date_solde=c.date_solde, reprise=c.reprise
                )
                for c in ligne.cellules
            ],
            total=ligne.total,
            depassement=ligne.depassement,
            **extra,
        )


class JourOut(LigneOut):
    date: dt.date


class BanquesTableOut(BaseModel):
    company_id: int
    date_fin: dt.date
    banques: list[BanqueColonneOut]
    ligne_total: Decimal | None
    # Du plus ancien au plus récent ; la date de fin en dernier
    jours: list[JourOut]
    disponible: LigneOut

    @classmethod
    def from_table(cls, company_id: int, table: TableauBanques) -> "BanquesTableOut":
        return cls(
            company_id=company_id,
            date_fin=table.date_fin,
            banques=[BanqueColonneOut.from_colonne(colonne) for colonne in table.banques],
            ligne_total=table.ligne_total,
            jours=[JourOut.from_ligne(jour.ligne, date=jour.date) for jour in table.jours],
            disponible=LigneOut.from_ligne(table.disponible),
        )
```

Note : `JourOut.from_ligne` hérite du classmethod de `LigneOut`. `cls(...)` construit donc bien un `JourOut`, et `date=` passe par `**extra`.

- [ ] **Step 6 : endpoint**

Dans `backend/app/api/position.py`, ajouter les imports :

```python
from app.schemas.position import BanquesTableOut
from app.services import position_banques_service, position_service, saisie_service
```

(remplace la ligne `from app.services import position_service, saisie_service`), puis ajouter la route **avant** `get_devises` :

```python
@router.get("/banques", response_model=BanquesTableOut)
def get_banques(
    company_id: CompanyId,
    jour: JourOuAujourdhui = None,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_view),
) -> BanquesTableOut:
    """Tableau Banques calculé à partir des soldes du jour, jusqu'à la date (jamais après aujourd'hui)."""
    table = position_banques_service.banques_table(db, company_id, jour)
    return BanquesTableOut.from_table(company_id, table)
```

- [ ] **Step 7 : lancer les tests et constater le succès**

Run : `docker compose run --rm backend pytest tests/test_position_banques_api.py tests/test_position_service.py tests/test_permissions.py -q`
Expected : tout passe. `test_permissions.py` confirme que la nouvelle route n'est pas publique.

- [ ] **Step 8 : suite complète et contrôles**

Run : `docker compose run --rm backend ruff check . ; docker compose run --rm backend ruff format --check . ; docker compose run --rm backend alembic check ; docker compose run --rm backend pytest -q`
Expected : `All checks passed!`, aucun fichier à reformater, `No new upgrade operations detected.`, et toute la suite au vert (516 tests existants plus les nouveaux).

- [ ] **Step 9 : ne pas commiter.**

---

### Task 3 : frontend, types, service et règles d'affichage

**Files :**
- Create : `frontend/types/position.ts`
- Create : `frontend/services/position.ts`
- Create : `frontend/lib/position.ts`
- Test : `frontend/lib/position.test.ts`

**Interfaces :**
- Consumes (tâche 2) : la réponse JSON de `GET /api/position/banques`.
- Produces :
  - types `BanqueColonne`, `CelluleBanque`, `LigneBanques`, `JourBanques`, `BanquesTable` ;
  - `getBanquesTable(companyId: number, jour: string): Promise<BanquesTable>` ;
  - `JOURS_AFFICHES = 10`, `formatTaux(pct: string | null): string`, `formatJour(iso: string): string`, `type Tone = "positive" | "negative" | "neutral"`, `signTone(value: string | null): Tone`.

- [ ] **Step 1 : écrire les tests qui échouent**

Créer `frontend/lib/position.test.ts` :

```ts
import { describe, expect, it } from "vitest";

import { formatJour, formatTaux, signTone } from "./position";

describe("formatTaux", () => {
  it("affiche au moins deux décimales, sans rien tronquer", () => {
    expect(formatTaux("5.5")).toBe("5,50 %");
    expect(formatTaux("5")).toBe("5,00 %");
    expect(formatTaux("4.125")).toBe("4,125 %");
  });

  it("affiche « - » sans taux, jamais 0", () => {
    expect(formatTaux(null)).toBe("-");
  });
});

describe("formatJour", () => {
  it("écrit la date comme le classeur, jj/mm/aa", () => {
    expect(formatJour("2026-09-30")).toBe("30/09/26");
  });
});

describe("signTone", () => {
  it("lit le signe sur le texte exact, sans conversion en nombre", () => {
    expect(signTone("300000.00")).toBe("positive");
    expect(signTone("0.01")).toBe("positive");
    expect(signTone("-100000.00")).toBe("negative");
  });

  it("zéro ou valeur inconnue : neutre", () => {
    expect(signTone("0.00")).toBe("neutral");
    expect(signTone("-0.00")).toBe("neutral");
    expect(signTone("0")).toBe("neutral");
    expect(signTone(null)).toBe("neutral");
  });
});
```

- [ ] **Step 2 : lancer les tests et constater l'échec**

Run (dans `frontend/`) : `npx vitest run lib/position.test.ts`
Expected : FAIL, `Failed to resolve import "./position"`.

- [ ] **Step 3 : écrire le code**

Créer `frontend/lib/position.ts` :

```ts
/** Affichage du tableau Banques. Les montants restent en texte exact : rien n'est recalculé ici. */

/** Jours « facilité de caisse » visibles d'abord ; les plus anciens derrière « Afficher plus ». */
export const JOURS_AFFICHES = 10;

/** Taux en % : « 5.5 » → « 5,50 % » (deux décimales au moins, jamais tronqué) ; absent → « - ». */
export function formatTaux(pct: string | null): string {
  if (pct === null) return "-";
  const [entier, decimales = ""] = pct.split(".");
  return `${entier},${decimales.padEnd(2, "0")} %`;
}

/** « 2026-09-30 » → « 30/09/26 », comme les dates du classeur. */
export function formatJour(iso: string): string {
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year.slice(2)}`;
}

export type Tone = "positive" | "negative" | "neutral";

/** Signe d'un montant exact, pour la couleur de Disponible Fc reel (vert > 0, rouge < 0). */
export function signTone(value: string | null): Tone {
  if (value === null || /^-?0*(\.0*)?$/.test(value)) return "neutral";
  return value.startsWith("-") ? "negative" : "positive";
}
```

Créer `frontend/types/position.ts` :

```ts
/** Tableau Banques calculé (`backend/app/schemas/position.py`). Montants en texte exact. */

export type BanqueColonne = {
  bank_id: number;
  code: string;
  logo: string | null;
  /** Compte courant MAD actif de la banque ; `null` sans compte (toute la colonne vaut « - »). */
  bank_account_id: number | null;
  taux_pct: string | null;
  ligne: string | null;
};

export type CelluleBanque = {
  bank_id: number;
  valeur: string | null;
  /** Date du solde utilisé ; `reprise` quand ce n'est pas le jour de la ligne. */
  date_solde: string | null;
  reprise: boolean;
};

export type LigneBanques = {
  cellules: CelluleBanque[];
  total: string | null;
  depassement: string | null;
};

export type JourBanques = LigneBanques & { date: string };

export type BanquesTable = {
  company_id: number;
  date_fin: string;
  banques: BanqueColonne[];
  ligne_total: string | null;
  /** Du plus ancien au plus récent ; la date de fin en dernier. */
  jours: JourBanques[];
  disponible: LigneBanques;
};
```

Créer `frontend/services/position.ts` :

```ts
import { apiFetch } from "@/lib/api";
import type { BanquesTable } from "@/types/position";

/** Tableau Banques calculé d'une société jusqu'à une date (« AAAA-MM-JJ »). */
export function getBanquesTable(companyId: number, jour: string) {
  const query = new URLSearchParams({ company_id: String(companyId), date: jour });
  return apiFetch<BanquesTable>(`/position/banques?${query}`);
}
```

- [ ] **Step 4 : lancer les tests et constater le succès**

Run (dans `frontend/`) : `npx vitest run lib/position.test.ts`
Expected : PASS, 5 tests.

- [ ] **Step 5 : ne pas commiter.**

---

### Task 4 : carte « Banques » sur `/position-bancaire`

**Files :**
- Create : `frontend/components/position/BanquesTable.tsx`
- Modify : `frontend/components/position/PositionView.tsx`

**Interfaces :**
- Consumes (tâche 3) : `getBanquesTable`, `JOURS_AFFICHES`, `formatTaux`, `formatJour`, `signTone`, `Tone`, les types de `types/position.ts`, plus `showLast` existant (`frontend/lib/statements.ts`), `GRID_TABLE` et `GRID_HEAD` (`GridCell.tsx`), `BankLabel`, `formatAmount`, `formatDate`.
- Produces : `BanquesTable({ companyId: number; jour: string })`.

Charger le skill `simtis-design` avant cette tâche (règle de CLAUDE.md pour tout travail d'interface).

- [ ] **Step 1 : écrire le composant**

Créer `frontend/components/position/BanquesTable.tsx` :

```tsx
"use client";

import { ChevronUp, Landmark } from "lucide-react";
import { useEffect, useState } from "react";

import { BankLabel } from "@/components/banks/BankLabel";
import { GRID_HEAD, GRID_TABLE } from "@/components/position/GridCell";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { formatDate } from "@/lib/balances";
import { cn } from "@/lib/cn";
import { formatAmount } from "@/lib/format";
import { JOURS_AFFICHES, formatJour, formatTaux, signTone, type Tone } from "@/lib/position";
import { showLast } from "@/lib/statements";
import { getBanquesTable } from "@/services/position";
import type { BanquesTable as Table, CelluleBanque, LigneBanques } from "@/types/position";

type LoadState = "loading" | "error" | "ready";

const NUMBER = "px-2 py-1.5 text-right tabular-nums whitespace-nowrap";
const ROW_HEAD = cn(GRID_HEAD, "text-left");
const GRID = cn(GRID_TABLE, "min-w-[860px] table-fixed");
// Disponible Fc reel : vert > 0, rouge < 0 (tokens de statut, pas le vert du classeur)
const TONES: Record<Tone, string> = {
  positive: "text-simtis-success",
  negative: "text-simtis-danger",
  neutral: "",
};

type BanquesTableProps = {
  companyId: number;
  /** Date de fin du tableau (« AAAA-MM-JJ ») ; l'API ne va jamais au-delà d'aujourd'hui. */
  jour: string;
};

/**
 * Tableau Banques du classeur, calculé par l'API à partir des soldes du jour (lecture seule) :
 * Taux, LIGNE, une ligne « facilité de caisse » par jour (solde + LIGNE), Disponible Fc reel.
 */
export function BanquesTable({ companyId, jour }: BanquesTableProps) {
  const [table, setTable] = useState<Table | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [retryKey, setRetryKey] = useState(0);
  const [shown, setShown] = useState(JOURS_AFFICHES);

  useEffect(() => {
    let cancelled = false;
    getBanquesTable(companyId, jour).then(
      (result) => {
        if (cancelled) return;
        setTable(result);
        setState("ready");
      },
      () => {
        if (!cancelled) setState("error");
      },
    );
    return () => {
      cancelled = true;
    };
  }, [companyId, jour, retryKey]);

  return (
    <Card title="Banques" icon={Landmark}>
      {state === "loading" && <LoadingState rows={4} />}
      {state === "error" && (
        <ErrorState
          message="Impossible de charger le tableau Banques."
          onRetry={() => {
            setState("loading");
            setRetryKey((key) => key + 1);
          }}
        />
      )}
      {state === "ready" && table && (
        <Grid
          table={table}
          shown={shown}
          onShowMore={() => setShown((count) => count + JOURS_AFFICHES)}
        />
      )}
    </Card>
  );
}

function Grid({
  table,
  shown,
  onShowMore,
}: {
  table: Table;
  shown: number;
  onShowMore: () => void;
}) {
  // Les jours les plus récents d'abord visibles ; ordre du classeur : le plus ancien en haut
  const visible = showLast(table.jours, shown, JOURS_AFFICHES);
  const columns = (
    <colgroup>
      <col className="w-[200px]" />
      {table.banques.map((banque) => (
        <col key={banque.bank_id} />
      ))}
      <col className="w-[130px]" />
      <col className="w-[130px]" />
    </colgroup>
  );

  return (
    <>
      {visible.hidden > 0 && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-sm">
          <p className="text-simtis-muted">
            {visible.rows.length} derniers jours sur {table.jours.length}
          </p>
          <Button
            variant="ghost"
            icon={ChevronUp}
            onClick={onShowMore}
            className="h-auto min-h-10 px-0 whitespace-normal"
          >
            Afficher {visible.next} {visible.next > 1 ? "jours plus anciens" : "jour plus ancien"}
          </Button>
        </div>
      )}
      {/* relative : le texte réservé aux lecteurs d'écran ne doit pas élargir la page */}
      <div className="relative overflow-x-auto">
        <table className={GRID} aria-label="Banques">
          {columns}
          <thead>
            <tr>
              <th scope="col" className={ROW_HEAD}>
                Banque
              </th>
              {table.banques.map((banque) => (
                <th key={banque.bank_id} scope="col" className={GRID_HEAD}>
                  <BankLabel code={banque.code} logo={banque.logo} layout="stacked" />
                </th>
              ))}
              <th scope="col" className={GRID_HEAD}>
                TOTAL
              </th>
              <th scope="col" className={GRID_HEAD}>
                DEPASSEMENT
              </th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row" className={ROW_HEAD}>
                Taux
              </th>
              {table.banques.map((banque) => (
                <td key={banque.bank_id} className={NUMBER}>
                  {formatTaux(banque.taux_pct)}
                </td>
              ))}
              <td />
              <td />
            </tr>
            <tr>
              <th
                scope="row"
                className={ROW_HEAD}
                title="LIGNE actuelle du compte, appliquée à tous les jours"
              >
                LIGNE
              </th>
              {table.banques.map((banque) => (
                <td key={banque.bank_id} className={NUMBER}>
                  {formatAmount(banque.ligne)}
                </td>
              ))}
              <td className={NUMBER}>{formatAmount(table.ligne_total)}</td>
              <td />
            </tr>
            {visible.rows.map((day) => (
              <tr key={day.date}>
                <th scope="row" className={ROW_HEAD}>
                  facilité de caisse <span className="tabular-nums">{formatJour(day.date)}</span>
                </th>
                <LineCells line={day} />
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {table.jours.length === 0 && (
        <p className="mt-3 text-sm text-simtis-muted">Aucun solde enregistré pour cette société.</p>
      )}
      {/* Ligne séparée sous le tableau, sur les mêmes colonnes */}
      <div className="relative mt-3 overflow-x-auto">
        <table className={GRID} aria-label="Disponible Fc reel">
          {columns}
          <tbody>
            <tr>
              <th scope="row" className={ROW_HEAD}>
                Disponible Fc reel
              </th>
              <LineCells line={table.disponible} colored />
            </tr>
          </tbody>
        </table>
      </div>
    </>
  );
}

function LineCells({ line, colored = false }: { line: LigneBanques; colored?: boolean }) {
  const tone = (value: string | null) => (colored ? TONES[signTone(value)] : "");
  return (
    <>
      {line.cellules.map((cellule) => (
        <AmountCell key={cellule.bank_id} cellule={cellule} className={tone(cellule.valeur)} />
      ))}
      <td className={cn(NUMBER, tone(line.total))}>{formatAmount(line.total)}</td>
      <td className={cn(NUMBER, tone(line.depassement))}>{formatAmount(line.depassement)}</td>
    </>
  );
}

/** Montant d'une banque ; un solde repris d'un jour précédent est grisé et daté. */
function AmountCell({ cellule, className }: { cellule: CelluleBanque; className: string }) {
  if (!cellule.reprise) {
    return <td className={cn(NUMBER, className)}>{formatAmount(cellule.valeur)}</td>;
  }
  const note = `dernier solde connu : ${formatDate(cellule.date_solde)}`;
  return (
    <td className={cn(NUMBER, "text-simtis-muted", className)} title={note}>
      {formatAmount(cellule.valeur)}
      <span className="sr-only"> ({note})</span>
    </td>
  );
}
```

- [ ] **Step 2 : brancher la carte dans la page**

Dans `frontend/components/position/PositionView.tsx` :

1. Ajouter l'import `import { BanquesTable } from "@/components/position/BanquesTable";` avant celui de `DevisesTable`.
2. Remplacer la docstring du composant par :

```tsx
/**
 * Page Position bancaire : tableau Banques calculé (P8.1), puis tableaux Devises et Prévisions de
 * la société active, saisis à la main pour une date (en attendant P9 et P14).
 */
```

3. Remplacer `description="Tableaux Devises et Prévisions de la société active, saisis à la main"` par `description="Tableau Banques calculé ; Devises et Prévisions saisis à la main"`.
4. Dans le fragment `loadState === "ready"`, ajouter en premier :

```tsx
          <BanquesTable
            key={`banques-${companyId}-${jour}`}
            companyId={companyId}
            jour={jour}
          />
```

La `key` remet le tableau aux 10 derniers jours quand la date ou la société change.

- [ ] **Step 3 : contrôles du frontend**

Run (dans `frontend/`) : `npx prettier --write components/position lib/position.ts lib/position.test.ts types/position.ts services/position.ts ; npm run lint ; npm run format:check ; npm run typecheck ; npm test ; npm run build`
Expected : lint sans erreur, « All matched files use Prettier code style! », tsc sans erreur, tous les tests Vitest au vert (155 existants et 5 nouveaux), puis « Compiled successfully ».

- [ ] **Step 4 : ne pas commiter.**

---

### Task 5 : contrôle Edge (lecture seule) et documentation

**Files :**
- Create (scratchpad, hors dépôt) : `comptes-banques.mjs` dans le dossier e2e du scratchpad qui contient `node_modules/playwright-core`
- Modify : `CLAUDE.md`, `docs/specs/Plan_Phases_Realisation_SIMTIS.md`, `.claude/skills/simtis-design/pages.md`

**Interfaces :**
- Consumes : la page `/position-bancaire` servie par `docker compose` (frontend sur 3000, API sur 8000), comptes de démo `tresorerie.demo@example.com` et `direction.demo@example.com`, mot de passe `Simtis-Demo-2026!`.
- Produces : un rapport « N/N contrôles réussis ».

Écart volontaire avec la spécification : le contrôle se fait en **lecture seule** sur les soldes déjà présents (société Simtis), sans créer puis supprimer de soldes de test. Il compare l'écran à la réponse de l'API, les calculs étant prouvés par les tests backend. Il n'y a donc aucun nettoyage, et aucun risque pour les données de l'utilisateur.

- [ ] **Step 1 : écrire le script**

```js
// Contrôle : tableau Banques calculé sur /position-bancaire. Lecture seule.
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const OUT = fileURLToPath(new URL(".", import.meta.url));
const PASSWORD = "Simtis-Demo-2026!";
const results = [];
const check = (label, ok, detail = "") => {
  results.push(!!ok);
  console.log(`${ok ? "OK  " : "ECHEC"} ${label}${detail ? ` — ${detail}` : ""}`);
};
const norm = (t) => t.replace(/[\s  ]+/g, " ").trim();
const browser = await chromium.launch({ channel: "msedge", headless: true });

async function open(email, viewport) {
  const page = await (await browser.newContext({ viewport })).newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("http://localhost:3000/login?next=%2Fposition-bancaire");
  await page.waitForSelector("#email", { timeout: 60000 });
  await page.fill("#email", email);
  await page.fill("#password", PASSWORD);
  const api = page.waitForResponse((r) => r.url().includes("/api/position/banques"), {
    timeout: 60000,
  });
  await page.click('form button[type="submit"]');
  const body = await (await api).json();
  await page.getByRole("table", { name: "Banques" }).waitFor({ timeout: 60000 });
  return { page, errors, body };
}

for (const [email, viewport] of [
  ["tresorerie.demo@example.com", { width: 1440, height: 900 }],
  ["direction.demo@example.com", { width: 1440, height: 900 }],
  ["tresorerie.demo@example.com", { width: 390, height: 844 }],
]) {
  const tag = `${email.split(".")[0]} ${viewport.width}px`;
  const { page, errors, body } = await open(email, viewport);
  const table = page.getByRole("table", { name: "Banques" });
  const headers = (await table.locator("thead th").allInnerTexts()).map(norm);
  check(
    `${tag} : en-têtes = banques de l'API + TOTAL, DEPASSEMENT`,
    headers.join("|") === ["Banque", ...body.banques.map((b) => b.code), "TOTAL", "DEPASSEMENT"].join("|"),
    headers.join("|"),
  );
  const rows = (await table.locator("tbody tr").allInnerTexts()).map(norm);
  check(`${tag} : Taux puis LIGNE`, rows[0].startsWith("Taux") && rows[1].startsWith("LIGNE"));
  const days = rows.slice(2);
  check(
    `${tag} : ${Math.min(10, body.jours.length)} jours visibles sur ${body.jours.length}`,
    days.length === Math.min(10, body.jours.length),
    String(days.length),
  );
  if (body.jours.length > 0) {
    const last = body.jours.at(-1);
    const [y, m, d] = last.date.split("-");
    check(`${tag} : dernier jour en bas`, days.at(-1).startsWith(`facilité de caisse ${d}/${m}/${y.slice(2)}`), days.at(-1));
  }
  const more = page.getByRole("button", { name: /jours? plus anciens?/ });
  check(`${tag} : « Afficher plus » seulement s'il y a plus de 10 jours`, (await more.count()) === (body.jours.length > 10 ? 1 : 0));
  if (body.jours.length > 10) {
    await more.click();
    const after = await table.locator("tbody tr").count();
    check(`${tag} : après clic, 10 jours de plus`, after - 2 === Math.min(20, body.jours.length), String(after - 2));
  }
  const dispo = page.getByRole("table", { name: "Disponible Fc reel" });
  const totalClass = await dispo.locator("td").nth(body.banques.length).getAttribute("class");
  const total = body.disponible.total;
  const expected = total === null || /^-?0*(\.0*)?$/.test(total) ? null : total.startsWith("-") ? "text-simtis-danger" : "text-simtis-success";
  check(`${tag} : couleur du TOTAL Disponible Fc reel`, expected === null || totalClass.includes(expected), `${total} ${totalClass}`);
  const pageWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  check(`${tag} : la page ne déborde pas`, pageWidth <= viewport.width, String(pageWidth));
  check(`${tag} : aucune erreur JavaScript`, errors.length === 0, errors.join(" | "));
  await page.screenshot({ path: `${OUT}banques-${email.split(".")[0]}-${viewport.width}.png`, fullPage: true });
  await page.context().close();
}

await browser.close();
const failed = results.filter((ok) => !ok).length;
console.log(`\n${results.length - failed}/${results.length} contrôles réussis`);
process.exit(failed ? 1 : 0);
```

- [ ] **Step 2 : lancer le contrôle**

Run : `node comptes-banques.mjs` depuis le dossier e2e du scratchpad, après `docker compose up -d --wait` et un rechargement du frontend.
Expected : « N/N contrôles réussis ». Regarder ensuite les captures `banques-*.png`, en attendant que les logos soient chargés avant de juger : une case de logo vide sur une capture prise trop tôt n'est pas un défaut.

- [ ] **Step 3 : documentation**

1. `CLAUDE.md`, section « Current state » : remplacer `Next: P8 (bank position).` par :
   `P8.1 (done, spec docs/superpowers/specs/2026-10-03-tableau-banques-design.md): the Banques table of /position-bancaire is computed by GET /api/position/banques?company_id=&date= (permission position.view, no migration): pure Decimal rules in position_service.tableau_banques, reads in position_repository, orchestration in position_banques_service; one « facilité de caisse » row per calendar day from the first balance to min(date, today), a day without balance reuses the bank's last known one (shown greyed, « dernier solde connu »), the last 10 days visible with « Afficher plus ». Next: P8.2 (detail table, filters) and P8.3 (chart).`
2. `docs/specs/Plan_Phases_Realisation_SIMTIS.md`, sous `### PHASE 8 — Position bancaire`, après la ligne `**Prérequis** : P7`, ajouter le bloc :
   `> **P8.1 — Tableau Banques calculé : réalisé le 03/10/2026** (spécification docs/superpowers/specs/2026-10-03-tableau-banques-design.md, plan docs/superpowers/plans/2026-10-03-tableau-banques.md). GET /api/position/banques?company_id=&date= (position.view, sans migration). Colonnes : banques actives, compte courant MAD actif de la société. Une ligne « facilité de caisse » par jour calendaire (solde du jour + LIGNE, dernier solde connu repris), DEPASSEMENT = TOTAL − somme des LIGNES, Disponible Fc reel = ligne de la date de fin ; 10 derniers jours visibles + « Afficher plus ». La LIGNE n'est pas historisée : les jours passés utilisent la LIGNE actuelle. Restent : P8.2 tableau détaillé et filtres, P8.3 graphique, recette sur l'Excel de Salma.`
3. `.claude/skills/simtis-design/pages.md`, section « Tableau « Banques » », ajouter sous la puce **facilité de caisse** :
   `  - Affichage : les 10 derniers jours visibles, au-dessus « N derniers jours sur M » et un bouton ghost « Afficher N jours plus anciens » (ChevronUp) ; une valeur reprise d'un jour précédent est en text-simtis-muted avec l'infobulle « dernier solde connu : JJ/MM/AAAA » ; sans aucun solde : « Aucun solde enregistré pour cette société. ». Carte « Banques » (icône Landmark), en premier sur /position-bancaire, lecture seule.`

- [ ] **Step 4 : vérification finale**

Run : toutes les commandes de « Global Constraints » (backend et frontend).
Expected : tout au vert, avec les résultats lus avant d'annoncer la fin.

- [ ] **Step 5 : ne pas commiter.**
