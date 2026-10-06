# Import Sage / SI et écritures comptables (P10) — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** importer les écritures de trésorerie d'un export Excel Sage / SI (lignes banque des journaux de banque, rattachées à leur compte bancaire par le journal Sage) et les consulter sur `/ecritures`.

**Architecture :** la lecture du classeur (feuille, en-tête, colonnes, correspondance par synonymes) sort de `import_service.py` vers un module commun `import_file.py`, paramétré par la liste des champs ; les relevés l'utilisent sans changer de comportement. Un nouveau `accounting_import_service.py` applique les règles des lignes comptables (analyse, confirmation, lecture paginée) ; un routeur `accounting` les expose. Côté frontend, un module `ecritures` reprend l'assistant Fichier → Validation (sans aperçu modifiable) et ajoute une liste paginée par le serveur.

**Tech Stack :** FastAPI, SQLAlchemy 2.1, Alembic, PostgreSQL 17, openpyxl, pytest ; Next.js 16, TypeScript, Tailwind v4, Vitest, Edge via playwright-core.

**Spec :** `docs/superpowers/specs/2026-10-05-import-sage-design.md`

## Global Constraints

- Français pour l'interface, les messages d'erreur, les commentaires et la documentation.
- SIMTIS n'est pas un second Sage : aucune écriture créée ni corrigée dans SIMTIS ; pas d'aperçu modifiable.
- Montants : `Decimal` côté serveur, texte exact dans l'API, jamais de `float` ; débit et crédit gardés tels que dans Sage ; `montant = credit − debit` (CHECK existant).
- Une seule société par import et par lecture ; jamais de mélange entre sociétés.
- Couches : `api/` mince → `services/` → `repositories/` → `models/` ; `NotFoundError` (404) / `ConflictError` (409) avec un message en français ; schémas d'entrée `extra="forbid"`.
- Permissions : import = `accounting.import` ; lecture = `accounting.import` OU `reconciliation.view` (`require_any_permission`) ; routeur dans `protected_router`.
- Fichier : `.xlsx` seulement, 5 Mo et 5 000 lignes au plus.
- Toute nouvelle contrainte (UNIQUE, index partiel) a son test dans `tests/test_constraints.py`.
- Ne jamais écrire de test dont le résultat dépend du décalage horaire du Maroc en 2026 (dates de test en 2025).
- **Aucun commit** : l'utilisateur commite lui-même. Les étapes « Commit » du modèle deviennent « Ne pas commiter ».
- Fin de travail : `ruff check`, `ruff format --check`, `pytest`, `alembic check` (backend) et `npm run lint && npm run format:check && npm run typecheck && npm test && npm run build` (frontend) passent.
- Contrôle Edge : données de test sur Tefil uniquement, nettoyées ensuite par un script SQL copié dans le conteneur (`docker compose cp`), jamais passé par PowerShell.

## Review Focus

1. **Journal Sage écrit en minuscules ou avec des espaces dans le fichier** (« bq1 », « BQ1 ») : la ligne doit être rattachée quand même. Test : `test_journal_is_matched_whatever_its_case` (tâche 3).
2. **Compte numérique lu par Excel comme un nombre** (5141 → `5141` int, ou `5141.0`) : il doit commencer par « 5141 ». Test : `test_numeric_account_cell_is_read_as_text` (tâche 3).
3. **Deux comptes bancaires avec le même journal** (un actif, un désactivé) : seul le compte actif reçoit les lignes. Test : `test_inactive_account_journal_is_ignored` (tâche 3).
4. **Recherche avec `%` ou `_`** dans la barre de recherche : cherchés comme des caractères, pas comme des jokers SQL. Test : `test_search_treats_like_wildcards_as_text` (tâche 5).
5. **Page demandée au-delà de la dernière** : liste vide, pas d'erreur, `total` exact. Test : `test_page_beyond_the_last_is_empty` (tâche 5).

---

## Structure des fichiers

| Fichier | Rôle |
|---|---|
| `backend/app/services/import_file.py` (créer) | Lecture d'un classeur et correspondance colonnes / champs, paramétrées par une liste de champs |
| `backend/app/services/import_service.py` (modifier) | Utilise `import_file` ; règles des relevés inchangées |
| `backend/alembic/versions/20261005_1500_0010_journal_sage.py` (créer) | Colonne `bank_accounts.journal_sage` + index unique partiel |
| `backend/app/models/referentiel.py`, `schemas/account.py`, `services/account_service.py`, `repositories/account_repository.py` (modifier) | Journal Sage d'un compte |
| `backend/app/services/accounting_import_service.py` (créer) | Champs comptables, lignes, analyse, confirmation, lecture paginée |
| `backend/app/repositories/accounting_repository.py` (créer) | Lectures et écritures des écritures et imports comptables |
| `backend/app/schemas/accounting.py` (créer) | Schémas de l'API comptable |
| `backend/app/api/accounting.py` (créer) + `api/router.py` (modifier) | Routes `/api/accounting/...` |
| `backend/tests/test_accounting_import_api.py`, `test_accounting_entries_api.py` (créer) | Tests de l'import et de la lecture |
| `frontend/types/accounting.ts`, `services/accounting.ts`, `lib/accounting.ts` (+ test) (créer) | Types, appels, règles pures |
| `frontend/components/ecritures/*.tsx` (créer), `app/(app)/ecritures/page.tsx` (modifier) | Page Écritures |
| `frontend/components/accounts/AccountFormModal.tsx`, `AccountsView.tsx`, `lib/accounts.ts`, `types/account.ts` (modifier) | Champ « Journal Sage » |

---

### Task 1 : lecture commune du classeur (`import_file.py`)

**Files :**
- Create : `backend/app/services/import_file.py`
- Modify : `backend/app/services/import_service.py:63-332` (constantes et fonctions de lecture)
- Test : `backend/tests/test_import_file.py` (créer) ; `backend/tests/test_statements_api.py` (inchangé, doit rester vert)

**Interfaces :**
- Produces :
  - `ImportField(code: str, libelle: str, obligatoire: bool, synonymes: tuple[str, ...])` (déplacé, réexporté par `import_service`)
  - `Column(index: int, lettre: str, entete: str, exemples: list[str])` (déplacé)
  - `Mapping = dict[str, int | None]`
  - `MAX_FILE_BYTES = 5 * 1024 * 1024`, `MAX_ROWS = 5000`, `HEADER_SCAN_ROWS = 30`
  - `check_file(fichier_nom: str, content: bytes) -> None` (409 : pas `.xlsx`, vide, trop gros)
  - `read_sheet(content: bytes, feuille: str | None) -> tuple[list[str], str, list[tuple]]`
  - `field_for_header(header: str, fields: Sequence[ImportField]) -> tuple[str | None, int]`
  - `detect_header(rows: list[tuple], fields) -> int`
  - `columns_of(header: tuple, data: list[tuple]) -> list[Column]`
  - `propose_mapping(columns, fields) -> Mapping`
  - `mapping_from_headers(saved: dict[str, str | None], columns, fields) -> Mapping | None`
  - `mapping_errors(mapping, width: int, fields, *, amount_codes=("debit", "credit", "montant")) -> list[str]`
  - `headers_of(mapping: Mapping, columns) -> dict[str, str] | None` (en-têtes à mémoriser ; `None` si une colonne associée n'a pas d'en-tête)

- [ ] **Step 1 : écrire les tests du module commun**

Créer `backend/tests/test_import_file.py` :

```python
"""Lecture commune d'un classeur d'import (relevés et exports comptables)."""

from io import BytesIO

import pytest
from openpyxl import Workbook

from app.services.errors import ConflictError
from app.services.import_file import (
    ImportField,
    check_file,
    columns_of,
    detect_header,
    mapping_errors,
    mapping_from_headers,
    propose_mapping,
    read_sheet,
)

FIELDS = (
    ImportField("date", "Date", True, ("date",)),
    ImportField("libelle", "Libellé", True, ("libelle",)),
    ImportField("debit", "Débit", False, ("debit",)),
    ImportField("credit", "Crédit", False, ("credit",)),
    ImportField("montant", "Montant signé", False, ("montant",)),
)


def xlsx(rows: list[list]) -> bytes:
    workbook = Workbook()
    for row in rows:
        workbook.active.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_header_is_detected_below_title_lines():
    _, _, rows = read_sheet(xlsx([["Titre"], [], ["Date", "Libellé", "Débit"], [1, "x", 2]]), None)

    assert detect_header(rows, FIELDS) == 2


def test_mapping_is_proposed_from_synonyms():
    _, _, rows = read_sheet(xlsx([["Date", "Libellé", "Crédit"], ["01/09/2025", "VIR", 5]]), None)
    columns = columns_of(rows[0], rows[1:])

    assert propose_mapping(columns, FIELDS) == {
        "date": 0,
        "libelle": 1,
        "debit": None,
        "credit": 2,
        "montant": None,
    }


def test_saved_headers_must_all_be_found():
    _, _, rows = read_sheet(xlsx([["Date", "Libellé", "Débit"]]), None)
    columns = columns_of(rows[0], [])

    assert mapping_from_headers({"date": "Date", "debit": "Débit"}, columns, FIELDS)["debit"] == 2
    assert mapping_from_headers({"date": "Date", "credit": "Crédit"}, columns, FIELDS) is None


def test_mapping_errors_name_the_missing_and_conflicting_fields():
    errors = mapping_errors({"date": 0, "libelle": None, "debit": 1, "montant": 1}, 3, FIELDS)

    assert "Colonne obligatoire non associée : Libellé." in errors
    assert "Choisissez Débit et Crédit, ou Montant signé, pas les deux." in errors
    assert "La colonne B est associée à plusieurs champs." in errors


@pytest.mark.parametrize(
    ("nom", "content", "message"),
    [
        ("export.csv", b"x", "Seuls les fichiers Excel .xlsx sont acceptés."),
        ("export.xlsx", b"", "Le fichier est vide."),
    ],
)
def test_check_file_refuses_wrong_files(nom, content, message):
    with pytest.raises(ConflictError, match=message):
        check_file(nom, content)
```

- [ ] **Step 2 : vérifier l'échec**

Run : `docker compose run --rm backend pytest tests/test_import_file.py -q`
Expected : erreur à la collecte, `ModuleNotFoundError: No module named 'app.services.import_file'`.

- [ ] **Step 3 : créer `backend/app/services/import_file.py`**

```python
"""Lecture d'un classeur d'import, commune aux relevés bancaires et aux exports comptables.

Fichiers Excel `.xlsx` seulement (décision §3.3), 5 Mo et 5 000 lignes au plus. La ligne d'en-tête
est celle qui reconnaît le plus de champs parmi les 30 premières ; la correspondance colonnes /
champs se propose par synonymes d'en-têtes, ou se reprend d'un modèle mémorisé (par en-tête).
"""

import zipfile
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from io import BytesIO

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.utils.exceptions import InvalidFileException

from app.services.errors import ConflictError
from app.services.normalization_service import clean_text, is_blank, normalize_header

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000
HEADER_SCAN_ROWS = 30
SAMPLES = 3

Mapping = dict[str, int | None]


@dataclass(frozen=True)
class ImportField:
    code: str
    libelle: str
    obligatoire: bool
    # En-têtes reconnus, déjà normalisés (`normalize_header`)
    synonymes: tuple[str, ...]


@dataclass
class Column:
    index: int
    lettre: str
    entete: str
    exemples: list[str]


def check_file(fichier_nom: str, content: bytes) -> None:
    if not fichier_nom.lower().endswith(".xlsx"):
        raise ConflictError("Seuls les fichiers Excel .xlsx sont acceptés.")
    if not content:
        raise ConflictError("Le fichier est vide.")
    if len(content) > MAX_FILE_BYTES:
        raise ConflictError("Fichier trop volumineux : 5 Mo au plus.")


def read_sheet(content: bytes, feuille: str | None) -> tuple[list[str], str, list[tuple]]:
    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except (InvalidFileException, zipfile.BadZipFile, KeyError, OSError, ValueError) as error:
        raise ConflictError(
            "Fichier illisible : ce n'est pas un classeur Excel .xlsx valide."
        ) from error
    try:
        names = list(workbook.sheetnames)
        name = feuille or names[0]
        if name not in names:
            raise ConflictError(f"Feuille introuvable dans le fichier : « {name} ».")
        rows: list[tuple] = []
        for row in workbook[name].iter_rows(values_only=True):
            rows.append(tuple(row))
            if len(rows) > MAX_ROWS + HEADER_SCAN_ROWS:
                raise ConflictError(f"Fichier trop long : {MAX_ROWS} lignes au plus par fichier.")
    finally:
        workbook.close()
    while rows and all(is_blank(cell) for cell in rows[-1]):
        rows.pop()
    if not rows:
        raise ConflictError(f"La feuille « {name} » est vide.")
    return names, name, rows


def field_for_header(header: str, fields: Sequence[ImportField]) -> tuple[str | None, int]:
    """Champ reconnu pour un en-tête, et la force de la correspondance (2 exacte, 1 début, 0 aucune)."""
    if not header:
        return None, 0
    for item in fields:
        if header in item.synonymes:
            return item.code, 2
    best, best_length = None, 0
    for item in fields:
        for synonym in item.synonymes:
            if header.startswith(synonym + " ") and len(synonym) > best_length:
                best, best_length = item.code, len(synonym)
    return best, 1 if best else 0


def detect_header(rows: list[tuple], fields: Sequence[ImportField]) -> int:
    """Index de la ligne d'en-tête : celle qui reconnaît le plus de champs, parmi les premières."""
    best_index, best_score = None, 0
    for index, row in enumerate(rows[:HEADER_SCAN_ROWS]):
        score = sum(1 for cell in row if field_for_header(normalize_header(cell), fields)[1])
        if score > best_score:
            best_index, best_score = index, score
    if best_index is not None and best_score >= 2:
        return best_index
    return next(i for i, row in enumerate(rows) if not all(is_blank(cell) for cell in row))


def _display(value: object) -> str:
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    return clean_text(value) or ""


def columns_of(header: tuple, data: list[tuple]) -> list[Column]:
    width = max([len(header), *(len(row) for row in data)])
    columns = []
    for index in range(width):
        values = [row[index] for row in data if index < len(row) and not is_blank(row[index])]
        title = clean_text(header[index]) if index < len(header) else None
        columns.append(
            Column(
                index=index,
                lettre=get_column_letter(index + 1),
                entete=title or "",
                exemples=[_display(value) for value in values[:SAMPLES]],
            )
        )
    return columns


def propose_mapping(columns: list[Column], fields: Sequence[ImportField]) -> Mapping:
    """Correspondance détectée : les correspondances exactes d'abord, puis les débuts d'en-tête."""
    mapping: Mapping = dict.fromkeys(item.code for item in fields)
    for strength in (2, 1):
        for column in columns:
            if column.index in mapping.values():
                continue
            code, found = field_for_header(normalize_header(column.entete), fields)
            if code and found == strength and mapping[code] is None:
                mapping[code] = column.index
    return mapping


def mapping_from_headers(
    saved: dict[str, str | None], columns: list[Column], fields: Sequence[ImportField]
) -> Mapping | None:
    """Modèle mémorisé (champ → en-tête), s'il retrouve toutes ses colonnes dans le fichier."""
    by_header = {
        normalize_header(column.entete): column.index for column in columns if column.entete
    }
    mapping: Mapping = dict.fromkeys(item.code for item in fields)
    for code, header in saved.items():
        if code not in mapping or header is None:
            continue
        index = by_header.get(normalize_header(header))
        if index is None:
            return None
        mapping[code] = index
    return mapping


def mapping_errors(
    mapping: Mapping,
    width: int,
    fields: Sequence[ImportField],
    *,
    amount_codes: tuple[str, str, str] = ("debit", "credit", "montant"),
) -> list[str]:
    labels = {item.code: item.libelle for item in fields}
    errors = []
    for code, index in mapping.items():
        if index is not None and not 0 <= index < width:
            errors.append(f"{labels[code]} : colonne inexistante dans le fichier.")
    used = Counter(index for index in mapping.values() if index is not None)
    for index, count in sorted(used.items()):
        if count > 1 and 0 <= index < width:
            errors.append(
                f"La colonne {get_column_letter(index + 1)} est associée à plusieurs champs."
            )
    for item in fields:
        if item.obligatoire and mapping.get(item.code) is None:
            errors.append(f"Colonne obligatoire non associée : {item.libelle}.")
    debit, credit, montant = amount_codes
    has_debit_credit = mapping.get(debit) is not None or mapping.get(credit) is not None
    if mapping.get(montant) is not None and has_debit_credit:
        errors.append("Choisissez Débit et Crédit, ou Montant signé, pas les deux.")
    elif mapping.get(montant) is None and not has_debit_credit:
        errors.append("Associez au moins une colonne de montant : Débit, Crédit ou Montant signé.")
    return errors


def headers_of(mapping: Mapping, columns: list[Column]) -> dict[str, str] | None:
    """En-têtes à mémoriser (champ → en-tête) ; `None` si une colonne associée n'a pas d'en-tête."""
    headers = {}
    for code, index in mapping.items():
        if index is None:
            continue
        if not columns[index].entete:
            return None
        headers[code] = columns[index].entete
    return headers
```

- [ ] **Step 4 : brancher `import_service.py` sur le module commun**

Dans `backend/app/services/import_service.py` :
1. Supprimer les définitions de `MAX_FILE_BYTES`, `MAX_ROWS`, `HEADER_SCAN_ROWS`, `SAMPLES`, de la classe `ImportField`, de la classe `Column`, de `Mapping`, et des fonctions `_read_sheet`, `_field_for_header`, `_detect_header`, `_display`, `_columns`. Les importer depuis `import_file` :

```python
from app.services import import_file
from app.services.import_file import (
    HEADER_SCAN_ROWS,
    MAX_FILE_BYTES,
    MAX_ROWS,
    Column,
    ImportField,
    Mapping,
)
```

2. Remplacer `propose_mapping`, `_saved_mapping` et `mapping_errors` par :

```python
def propose_mapping(columns: list[Column]) -> Mapping:
    return import_file.propose_mapping(columns, STATEMENT_FIELDS)


def _saved_mapping(db: Session, bank_id: int, columns: list[Column]) -> Mapping | None:
    """Modèle mémorisé pour la banque (champ → en-tête), s'il retrouve toutes ses colonnes."""
    saved = import_repository.latest_mapping(db, bank_id, TYPE_IMPORT)
    if saved is None:
        return None
    return import_file.mapping_from_headers(saved.mapping, columns, STATEMENT_FIELDS)


def mapping_errors(mapping: Mapping, width: int) -> list[str]:
    return import_file.mapping_errors(mapping, width, STATEMENT_FIELDS)
```

3. Dans `analyse_statement`, remplacer les contrôles de fichier et la lecture par :

```python
    import_file.check_file(fichier_nom, content)
    feuilles, feuille, rows = import_file.read_sheet(content, feuille)
    header_index = import_file.detect_header(rows, STATEMENT_FIELDS)
    data = rows[header_index + 1 :]
    if len(data) > MAX_ROWS:
        raise ConflictError(f"Fichier trop long : {MAX_ROWS} lignes au plus par relevé.")
    columns = import_file.columns_of(rows[header_index], data)
```

(le contrôle « compte inactif » reste avant ; les trois `if` « .xlsx / vide / 5 Mo » de la fonction sont remplacés par `check_file`, dont les messages sont identiques).

4. Rechercher dans le fichier tout autre appel aux anciens noms (`_columns`, `_detect_header`, `_read_sheet`) et les remplacer de la même façon.

- [ ] **Step 5 : vérifier que tout est vert**

Run : `docker compose run --rm backend pytest tests/test_import_file.py tests/test_statements_api.py -q`
Expected : tous les tests passent (5 nouveaux + les tests existants des relevés). Puis `ruff check .` et `ruff format --check .` propres.

Note : le message « Fichier trop long … par relevé » reste celui de `analyse_statement` ; celui de `read_sheet` (fichier très long avant l'en-tête) devient « par fichier ». Si un test existant attend « par relevé » sur ce second cas, garder « par relevé » dans le test et ajouter une règle au journal (ruling) plutôt que de modifier le comportement.

- [ ] **Step 6 : ne pas commiter.**

---

### Task 2 : journal Sage d'un compte bancaire

**Files :**
- Create : `backend/alembic/versions/20261005_1500_0010_journal_sage.py`
- Modify : `backend/app/models/referentiel.py` (classe `BankAccount`), `backend/app/schemas/account.py`, `backend/app/services/account_service.py`, `backend/app/repositories/account_repository.py`
- Test : `backend/tests/test_accounts_api.py`, `backend/tests/test_constraints.py`, `backend/tests/test_migrations.py`

**Interfaces :**
- Produces : `BankAccount.journal_sage: str | None` ; `AccountOut.journal_sage` ; `AccountCreate.journal_sage: str | None = None` ; `AccountUpdate.journal_sage: str | None` (obligatoire, comme `compte_comptable`) ; `account_repository.find_active_by_journal(db, *, company_id: int, journal: str) -> BankAccount | None`.

- [ ] **Step 1 : tests**

Dans `backend/tests/test_accounts_api.py`, ajouter `"journal_sage": account.journal_sage,` dans `update_body`, puis à la fin :

```python
# --- Journal Sage (P10) ---------------------------------------------------------------------------


def test_journal_sage_is_saved_in_capitals(client, tresorerie, db):
    response = client.post(ACCOUNTS, json=payload(db, journal_sage=" bq1 "), headers=tresorerie)

    assert response.status_code == 201
    assert response.json()["journal_sage"] == "BQ1"


@pytest.mark.parametrize("journal", ["BQ-1", "TROPLONGJOURNAL"])
def test_invalid_journal_sage_gives_422(client, tresorerie, db, journal):
    assert client.post(ACCOUNTS, json=payload(db, journal_sage=journal), headers=tresorerie).status_code == 422


def test_journal_sage_used_by_another_active_account_is_refused(client, tresorerie, db):
    add(db, "SIMTIS", "AWB", journal_sage="BQ1")
    account = add(db, "SIMTIS", "CIH")

    response = client.put(
        f"{ACCOUNTS}/{account.id}", json=update_body(account, journal_sage="BQ1"), headers=tresorerie
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Le journal Sage BQ1 est déjà celui du compte AWB MAD de cette société."
    }


def test_same_journal_in_another_company_is_accepted(client, tresorerie, db):
    add(db, "SOCX", "AWB", journal_sage="BQ1")
    account = add(db, "SIMTIS", "CIH")

    response = client.put(
        f"{ACCOUNTS}/{account.id}", json=update_body(account, journal_sage="BQ1"), headers=tresorerie
    )

    assert response.status_code == 200


def test_journal_sage_change_is_audited(client, tresorerie, db):
    account = add(db, "SIMTIS", "CIH")

    client.put(
        f"{ACCOUNTS}/{account.id}", json=update_body(account, journal_sage="BQ3"), headers=tresorerie
    )

    [entry] = audit(db, "modification_compte")
    assert entry.nouvelle_valeur == {"journal_sage": "BQ3"}


def test_reactivating_an_account_whose_journal_is_taken_is_refused(client, tresorerie, db):
    old = add(db, "SIMTIS", "AWB", journal_sage="BQ1", actif=False)
    add(db, "SIMTIS", "CIH", journal_sage="BQ1")

    response = client.patch(f"{ACCOUNTS}/{old.id}/status", json={"actif": True}, headers=tresorerie)

    assert response.status_code == 409
    assert "BQ1" in response.json()["detail"]
```

Dans `backend/tests/test_constraints.py`, à la fin (avec `build_account` et `make_world` déjà importés en tête du fichier ; sinon les importer de `tests.helpers`) :

```python
# --- Journal Sage (migration 0010) ----------------------------------------------------------------


def test_one_active_account_per_sage_journal_and_company(db, world):
    other_bank = save(db, build_bank())
    save(db, build_account(world.company, other_bank, journal_sage="BQ1"))

    assert_rejected(
        db,
        "uq_bank_accounts_journal_sage_actif",
        build_account(world.company, save(db, build_bank()), journal_sage="BQ1"),
    )


def test_inactive_account_frees_its_sage_journal(db, world):
    save(db, build_account(world.company, save(db, build_bank()), journal_sage="BQ1", actif=False))
    save(db, build_account(world.company, save(db, build_bank()), journal_sage="BQ1"))
```

Dans `backend/tests/test_migrations.py`, ajouter avant `test_migration_matches_models` :

```python
def test_migration_0010_adds_an_empty_sage_journal(empty_database):
    config, engine = empty_database
    command.upgrade(config, "0009")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO companies (id, code, nom) OVERRIDING SYSTEM VALUE VALUES (1, 'C', 'Société');
                INSERT INTO banks (id, code, nom) OVERRIDING SYSTEM VALUE VALUES (1, 'B', 'Banque');
                INSERT INTO currencies (code, libelle) VALUES ('MAD', 'Dirham');
                INSERT INTO bank_accounts (company_id, bank_id, libelle, numero, devise)
                    VALUES (1, 1, 'Compte', 'N1', 'MAD');
                """
            )
        )

    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT journal_sage FROM bank_accounts")).scalar() is None

    command.downgrade(config, "0009")
    with engine.connect() as connection:
        columns = {row[0] for row in connection.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'bank_accounts'"
        ))}
    assert "journal_sage" not in columns
```

(Le helper `build_account` accepte des champs supplémentaires (`**over`) : `journal_sage` passe dès que le modèle l'a.)

- [ ] **Step 2 : vérifier l'échec**

Run : `docker compose run --rm backend pytest tests/test_accounts_api.py tests/test_constraints.py tests/test_migrations.py -q`
Expected : échecs (`journal_sage` inconnu, 422 sur `update_body`, migration 0010 absente).

- [ ] **Step 3 : modèle et migration**

Dans `backend/app/models/referentiel.py`, classe `BankAccount` : ajouter le champ et l'index.

```python
    # Code du journal de banque dans Sage (ex. BQ1) : rattache les écritures importées (P10)
    journal_sage: Mapped[str | None] = mapped_column(String(10))
```

et dans `__table_args__` :

```python
        Index(
            "uq_bank_accounts_journal_sage_actif",
            "company_id",
            "journal_sage",
            unique=True,
            postgresql_where=text("journal_sage IS NOT NULL AND actif"),
        ),
```

(importer `Index` et `text` si ce n'est pas déjà fait).

Créer `backend/alembic/versions/20261005_1500_0010_journal_sage.py` :

```python
"""journal sage

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-05 15:00:00

Journal de banque Sage de chaque compte bancaire (P10) : rattache une écriture importée de Sage à son
compte bancaire. Un journal ne sert qu'à un compte actif par société.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("bank_accounts", sa.Column("journal_sage", sa.String(length=10), nullable=True))
    op.create_index(
        "uq_bank_accounts_journal_sage_actif",
        "bank_accounts",
        ["company_id", "journal_sage"],
        unique=True,
        postgresql_where=sa.text("journal_sage IS NOT NULL AND actif"),
    )


def downgrade() -> None:
    op.drop_index("uq_bank_accounts_journal_sage_actif", table_name="bank_accounts")
    op.drop_column("bank_accounts", "journal_sage")
```

- [ ] **Step 4 : schéma, dépôt et service**

`backend/app/schemas/account.py` :

```python
JOURNAL_SAGE_PATTERN = re.compile(r"^[A-Z0-9]{1,10}$")


def _clean_journal_sage(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    value = value.strip().upper()
    if not JOURNAL_SAGE_PATTERN.match(value):
        raise ValueError("Le journal Sage contient 1 à 10 lettres ou chiffres (ex. BQ1).")
    return value
```

`AccountOut` : `journal_sage: str | None` et `journal_sage=account.journal_sage` dans `from_model`. `AccountCreate` : `journal_sage: str | None = None` + `_journal = field_validator("journal_sage")(_clean_journal_sage)`. `AccountUpdate` : `journal_sage: str | None` (sans valeur par défaut) + le même validateur.

`backend/app/repositories/account_repository.py` :

```python
def find_active_by_journal(db: Session, *, company_id: int, journal: str) -> BankAccount | None:
    """Le compte actif de la société qui porte déjà ce journal Sage, s'il existe."""
    query = select(BankAccount).where(
        BankAccount.company_id == company_id,
        BankAccount.journal_sage == journal,
        BankAccount.actif.is_(True),
    )
    return db.scalar(query)
```

`backend/app/services/account_service.py` :
- ajouter `"journal_sage"` à la fin de `EDITABLE_FIELDS` ;
- ajouter :

```python
def _check_journal_free(
    db: Session, *, company_id: int, journal: str | None, account_id: int | None = None
) -> None:
    if journal is None:
        return
    occupant = account_repository.find_active_by_journal(db, company_id=company_id, journal=journal)
    if occupant is not None and occupant.id != account_id:
        raise ConflictError(
            f"Le journal Sage {journal} est déjà celui du compte "
            f"{occupant.bank.code} {occupant.devise} de cette société."
        )
```

- `create_account` : paramètre `journal_sage: str | None = None` ; appeler `_check_journal_free(db, company_id=company.id, journal=journal_sage)` après `_check_slot_free` ; `journal_sage=journal_sage` dans le constructeur `BankAccount(...)`.
- `update_account` : paramètre `journal_sage: str | None` ; `"journal_sage": journal_sage` dans `new_values` ; si `"journal_sage" in changed and account.actif` → `_check_journal_free(db, company_id=account.company_id, journal=journal_sage, account_id=account.id)`.
- `set_account_status` : à la réactivation, après `_check_slot_free`, appeler `_check_journal_free(db, company_id=account.company_id, journal=account.journal_sage, account_id=account.id)`.

L'API (`backend/app/api/accounts.py`) passe `**body.model_dump()` : aucun changement.

- [ ] **Step 5 : vérifier**

Run : `docker compose run --rm backend pytest tests/test_accounts_api.py tests/test_constraints.py tests/test_migrations.py -q` puis `docker compose run --rm backend alembic check`
Expected : tout passe ; « No new upgrade operations detected. »

- [ ] **Step 6 : ne pas commiter.**

---

### Task 3 : analyse d'un export Sage

**Files :**
- Create : `backend/app/services/accounting_import_service.py`, `backend/app/repositories/accounting_repository.py`, `backend/app/schemas/accounting.py`, `backend/app/api/accounting.py`
- Modify : `backend/app/api/router.py`
- Test : `backend/tests/test_accounting_import_api.py`

**Interfaces :**
- Consumes : `import_file.*` (tâche 1), `BankAccount.journal_sage` (tâche 2), `normalization_service.parse_date / parse_amount / clean_libelle / clean_text / is_blank / line_hash / file_hash / normalize_header`.
- Produces :
  - `accounting_import_service.ACCOUNTING_FIELDS: tuple[ImportField, ...]`, `TYPE_IMPORT = "Comptabilité"`
  - `@dataclass EntryLine(numero, statut, motifs, date_ecriture, journal, compte, libelle, reference, debit, credit, montant, numero_piece, echeance, tiers, bank_account_id, bank_code, hash_ligne, doublon_de)`
  - `@dataclass EntriesSummary(nb_lignes, nb_valides, nb_erreurs, nb_doublons, nb_ignorees, total_debit, total_credit, periode_debut, periode_fin, par_compte: list[AccountTotal])` avec `AccountTotal(bank_account_id, bank_code, nb, total_debit, total_credit)`
  - `@dataclass AccountingAnalysis(company, fichier_nom, fichier_hash, deja_importe, feuilles, feuille, ligne_entete, colonnes, mapping, mapping_source, erreurs_mapping, lignes, resume)`
  - `analyse_entries(db, *, company_id: int, fichier_nom: str, content: bytes, mapping: Mapping | None = None, feuille: str | None = None, today: date | None = None) -> AccountingAnalysis`
  - `accounting_repository.bank_journals(db, company_id) -> list[BankAccount]` (actifs avec journal), `existing_entry_hashes(db, company_id, hashes) -> set[str]`, `latest_company_mapping(db, company_id, type_import) -> ColumnMapping | None`
  - `POST /api/accounting/import/analyse` → `AnalyseComptableOut`

- [ ] **Step 1 : tests**

Créer `backend/tests/test_accounting_import_api.py` :

```python
"""Import d'un export Sage / SI (P10) : analyse et confirmation."""

import json
from datetime import date
from decimal import Decimal
from io import BytesIO
from itertools import count

import pytest
from openpyxl import Workbook
from sqlalchemy import func, select

from app.models import AccountingEntry, AuditLog, Bank, BankAccount, ColumnMapping, Company, ImportBatch
from tests.helpers import bearer, build_account, login, make_auth_user, save

ANALYSE = "/api/accounting/import/analyse"
CONFIRM = "/api/accounting/import/confirm"
HEADER = ["Date", "Journal", "Compte", "N° pièce", "Libellé", "Débit", "Crédit", "Échéance", "Tiers"]
_numeros = count(1)


def xlsx(rows: list[list]) -> bytes:
    workbook = Workbook()
    for row in rows:
        workbook.active.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


EXPORT = [
    ["Grand livre — export Sage"],
    HEADER,
    [date(2025, 9, 2), "BQ1", "5141", "P001", "REG CLIENT ATLAS", 38500, None, None, "ATLAS"],
    [date(2025, 9, 2), "BQ1", "3421", "P001", "REG CLIENT ATLAS", None, 38500, None, "ATLAS"],
    [date(2025, 9, 3), "BQ2", "5141", "P002", "VIR FOURNISSEUR TEXTILE", None, 12800, date(2025, 9, 30), None],
    [date(2025, 9, 3), "ACH", "4411", "F77", "FACTURE ACHAT", None, 500, None, "TEXTILE"],
]


@pytest.fixture
def comptable(client, reference) -> dict[str, str]:
    make_auth_user(reference, "COMPTABLE", email="comptable@example.com")
    return bearer(login(client, "comptable@example.com"))


@pytest.fixture
def direction(client, reference) -> dict[str, str]:
    make_auth_user(reference, "DIRECTION", email="direction@example.com")
    return bearer(login(client, "direction@example.com"))


def company(db, code: str = "SIMTIS") -> Company:
    return db.scalar(select(Company).filter_by(code=code))


def account(db, bank_code: str, journal: str | None, company_code: str = "SIMTIS", **over) -> BankAccount:
    over.setdefault("numero", f"RIB-CPT-{next(_numeros):06d}")
    over.setdefault("compte_comptable", "5141")
    bank = db.scalar(select(Bank).filter_by(code=bank_code))
    return save(db, build_account(company(db, company_code), bank, journal_sage=journal, **over))


@pytest.fixture
def journals(db, reference) -> tuple[BankAccount, BankAccount]:
    return account(db, "AWB", "BQ1"), account(db, "BP", "BQ2")


def post(client, url, headers, db, content, *, code="SIMTIS", nom="export.xlsx", **form):
    data = {"company_id": str(company(db, code).id), **form}
    if isinstance(data.get("mapping"), dict):
        data["mapping"] = json.dumps(data["mapping"])
    files = {"fichier": (nom, content, "application/octet-stream")}
    return client.post(url, data=data, files=files, headers=headers)


def analyse(client, headers, db, content, **form):
    return post(client, ANALYSE, headers, db, content, **form)


def test_bank_lines_are_kept_and_attached_by_their_journal(client, comptable, db, journals):
    awb, bp = journals

    response = analyse(client, comptable, db, xlsx(EXPORT))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ligne_entete"] == 2
    assert body["mapping_source"] == "Détection"
    assert body["erreurs_mapping"] == []
    lines = body["lignes"]
    assert [(line["journal"], line["compte"], line["bank_account_id"], line["statut"]) for line in lines] == [
        ("BQ1", "5141", awb.id, "Valide"),
        ("BQ2", "5141", bp.id, "Valide"),
    ]
    assert lines[0] | {"hash_ligne": None} == {
        "numero": 3,
        "statut": "Valide",
        "motifs": [],
        "date_ecriture": "2025-09-02",
        "journal": "BQ1",
        "compte": "5141",
        "libelle": "REG CLIENT ATLAS",
        "reference": None,
        "debit": "38500.00",
        "credit": "0.00",
        "montant": "-38500.00",
        "numero_piece": "P001",
        "echeance": None,
        "tiers": "ATLAS",
        "bank_account_id": awb.id,
        "bank_code": "AWB",
        "hash_ligne": None,
        "doublon_de": None,
    }
    assert lines[1]["echeance"] == "2025-09-30"
    resume = body["resume"]
    assert (resume["nb_valides"], resume["nb_ignorees"], resume["nb_erreurs"]) == (2, 2, 0)
    assert (resume["total_debit"], resume["total_credit"]) == ("38500.00", "12800.00")
    assert (resume["periode_debut"], resume["periode_fin"]) == ("2025-09-02", "2025-09-03")
    assert [item["bank_code"] for item in resume["par_compte"]] == ["AWB", "BP"]


def test_journal_is_matched_whatever_its_case(client, comptable, db, journals):
    rows = [HEADER, [date(2025, 9, 2), " bq1 ", "5141", "P1", "VIR", 10, None, None, None]]

    [line] = analyse(client, comptable, db, xlsx(rows)).json()["lignes"]

    assert (line["journal"], line["bank_code"]) == ("BQ1", "AWB")


def test_numeric_account_cell_is_read_as_text(client, comptable, db, journals):
    rows = [HEADER, [date(2025, 9, 2), "BQ1", 514100, "P1", "VIR", 10, None, None, None]]

    [line] = analyse(client, comptable, db, xlsx(rows)).json()["lignes"]

    assert (line["compte"], line["statut"]) == ("514100", "Valide")


def test_bank_account_without_accounting_code_keeps_every_line_of_its_journal(client, comptable, db, reference):
    account(db, "AWB", "BQ1", compte_comptable=None)
    rows = [HEADER, [date(2025, 9, 2), "BQ1", "3421", "P1", "VIR", 10, None, None, None]]

    assert len(analyse(client, comptable, db, xlsx(rows)).json()["lignes"]) == 1


def test_inactive_account_journal_is_ignored(client, comptable, db, reference):
    account(db, "AWB", "BQ1", actif=False)
    active = account(db, "CIH", "BQ1")

    [line] = analyse(client, comptable, db, xlsx(EXPORT[:3])).json()["lignes"]

    assert line["bank_account_id"] == active.id


def test_signed_amount_column(client, comptable, db, journals):
    rows = [
        ["Date", "Journal", "Compte", "Libellé", "Montant"],
        [date(2025, 9, 2), "BQ1", "5141", "VIR RECU", 100],
        [date(2025, 9, 3), "BQ1", "5141", "VIR EMIS", -40],
    ]

    lines = analyse(client, comptable, db, xlsx(rows)).json()["lignes"]

    assert [(line["debit"], line["credit"]) for line in lines] == [("0.00", "100.00"), ("40.00", "0.00")]


@pytest.mark.parametrize(
    ("cells", "motif"),
    [
        ({1: None}, "Date manquante."),
        ({1: "31/02/2025"}, "Date : Date illisible"),
        ({5: None}, "Libellé manquant."),
        ({6: "dix"}, "Débit : Montant illisible"),
        ({6: None}, "Montant manquant ou nul."),
        ({7: 5}, "Débit et crédit renseignés sur la même ligne."),
        ({8: "plus tard"}, "Échéance : Date illisible"),
        ({9: "T" * 121}, "Tiers : 120 caractères au plus."),
    ],
)
def test_invalid_bank_lines_are_errors(client, comptable, db, journals, cells, motif):
    row = [date(2025, 9, 2), "BQ1", "5141", "P1", "VIR", 10, None, None, None]
    for index, value in cells.items():
        row[index - 1] = value

    [line] = analyse(client, comptable, db, xlsx([HEADER, row])).json()["lignes"]

    assert line["statut"] == "Erreur"
    assert any(text.startswith(motif) for text in line["motifs"]), line["motifs"]


def test_future_date_is_an_error(client, comptable, db, journals):
    row = [date(2099, 1, 1), "BQ1", "5141", "P1", "VIR", 10, None, None, None]

    [line] = analyse(client, comptable, db, xlsx([HEADER, row])).json()["lignes"]

    assert "Date dans le futur." in line["motifs"]


def test_identical_lines_in_the_file_are_duplicates(client, comptable, db, journals):
    row = [date(2025, 9, 2), "BQ1", "5141", "P1", "FRAIS", 10, None, None, None]

    lines = analyse(client, comptable, db, xlsx([HEADER, row, row])).json()["lignes"]

    assert [(line["statut"], line["doublon_de"]) for line in lines] == [("Valide", None), ("Doublon", 2)]


def test_company_without_sage_journal_is_refused(client, comptable, db, reference):
    account(db, "AWB", None)

    response = analyse(client, comptable, db, xlsx(EXPORT))

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Renseignez le journal Sage de vos comptes bancaires (écran Comptes)."
    }


def test_journals_of_another_company_are_never_used(client, comptable, db, reference):
    account(db, "AWB", "BQ1", company_code="SOCX")
    account(db, "BP", "BQ9")

    body = analyse(client, comptable, db, xlsx(EXPORT)).json()

    assert body["lignes"] == []
    assert body["resume"]["nb_ignorees"] == 4


def test_unrecognised_columns_give_mapping_errors(client, comptable, db, journals):
    rows = [["A", "B", "C"], [date(2025, 9, 2), "BQ1", 10]]

    body = analyse(client, comptable, db, xlsx(rows)).json()

    assert "Colonne obligatoire non associée : Date." in body["erreurs_mapping"]
    assert body["lignes"] == []


def test_analysis_writes_nothing(client, comptable, db, journals):
    before = db.scalar(select(func.count()).select_from(AccountingEntry))

    analyse(client, comptable, db, xlsx(EXPORT))

    assert db.scalar(select(func.count()).select_from(AccountingEntry)) == before


def test_direction_cannot_import(client, direction, db, journals):
    assert analyse(client, direction, db, xlsx(EXPORT)).status_code == 403


def test_requires_a_token(client, reference):
    assert client.post(ANALYSE).status_code == 401
```

- [ ] **Step 2 : vérifier l'échec**

Run : `docker compose run --rm backend pytest tests/test_accounting_import_api.py -q`
Expected : échecs avec 404 (route absente) ; `test_requires_a_token` peut déjà passer.

- [ ] **Step 3 : dépôt `backend/app/repositories/accounting_repository.py`**

```python
"""Lectures et écritures des écritures comptables importées (P10)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AccountingEntry, BankAccount, ColumnMapping


def bank_journals(db: Session, company_id: int) -> list[BankAccount]:
    """Comptes bancaires actifs de la société qui ont un journal Sage."""
    query = select(BankAccount).where(
        BankAccount.company_id == company_id,
        BankAccount.actif.is_(True),
        BankAccount.journal_sage.is_not(None),
    )
    return list(db.scalars(query))


def existing_entry_hashes(db: Session, company_id: int, hashes: list[str]) -> set[str]:
    if not hashes:
        return set()
    query = select(AccountingEntry.hash_ligne).where(
        AccountingEntry.company_id == company_id, AccountingEntry.hash_ligne.in_(hashes)
    )
    return set(db.scalars(query))


def latest_company_mapping(db: Session, company_id: int, type_import: str) -> ColumnMapping | None:
    query = (
        select(ColumnMapping)
        .where(ColumnMapping.company_id == company_id, ColumnMapping.type == type_import)
        .order_by(ColumnMapping.updated_at.desc(), ColumnMapping.id.desc())
        .limit(1)
    )
    return db.scalar(query)


def add(db: Session, row: object) -> None:
    db.add(row)
```

- [ ] **Step 4 : service `backend/app/services/accounting_import_service.py` (analyse)**

```python
"""Import des écritures comptables d'un export Sage / SI (P10), en deux temps : analyse, puis
confirmation. SIMTIS n'est pas un second Sage : aucune écriture n'est créée ni corrigée ici.

Règles (décisions du 05/10/2026) :
- le fichier est importé pour une société ; seules les lignes d'un journal de banque sont retenues :
  journal = `journal_sage` d'un compte bancaire actif de la société, et compte qui commence par le
  `compte_comptable` de ce compte bancaire (s'il est renseigné) ; les autres lignes sont ignorées ;
- débit et crédit sont gardés tels que dans Sage ; une ligne en erreur se corrige dans Sage ;
- doublon : ligne déjà importée pour la société, ou identique à une autre ligne du fichier.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import BankAccount, Company
from app.repositories import account_repository, accounting_repository, import_repository
from app.services import import_file, position_service
from app.services.errors import ConflictError, NotFoundError
from app.services.import_file import Column, ImportField, Mapping
from app.services.normalization_service import (
    clean_libelle,
    clean_text,
    file_hash,
    is_blank,
    line_hash,
    parse_amount,
    parse_date,
)

TYPE_IMPORT = "Comptabilité"
JOURNAL_MAX = 20
COMPTE_MAX = 20
REFERENCE_MAX = 60
PIECE_MAX = 60
TIERS_MAX = 120

ACCOUNTING_FIELDS: tuple[ImportField, ...] = (
    ImportField("date_ecriture", "Date", True, ("date", "date ecriture", "date piece", "date comptable")),
    ImportField("journal", "Journal", True, ("journal", "code journal", "jnl")),
    ImportField("compte", "Compte", True, ("compte", "compte general", "n compte", "numero de compte")),
    ImportField("libelle", "Libellé", True, ("libelle", "libelle ecriture", "intitule")),
    ImportField("reference", "Référence", False, ("reference", "ref")),
    ImportField("debit", "Débit", False, ("debit", "montant debit")),
    ImportField("credit", "Crédit", False, ("credit", "montant credit")),
    ImportField("montant", "Montant signé", False, ("montant", "montant signe")),
    ImportField("numero_piece", "N° pièce", False, ("n piece", "numero piece", "piece", "no piece")),
    ImportField("echeance", "Échéance", False, ("echeance", "date echeance")),
    ImportField("tiers", "Tiers", False, ("tiers", "compte tiers", "client fournisseur")),
)
FIELD_LABELS = {item.code: item.libelle for item in ACCOUNTING_FIELDS}


@dataclass
class EntryLine:
    numero: int
    statut: str  # Valide / Erreur / Doublon
    motifs: list[str]
    date_ecriture: date | None = None
    journal: str | None = None
    compte: str | None = None
    libelle: str | None = None
    reference: str | None = None
    debit: Decimal | None = None
    credit: Decimal | None = None
    montant: Decimal | None = None
    numero_piece: str | None = None
    echeance: date | None = None
    tiers: str | None = None
    bank_account_id: int | None = None
    bank_code: str | None = None
    hash_ligne: str | None = None
    doublon_de: int | None = None


@dataclass
class AccountTotal:
    bank_account_id: int
    bank_code: str
    nb: int = 0
    total_debit: Decimal = Decimal("0.00")
    total_credit: Decimal = Decimal("0.00")


@dataclass
class EntriesSummary:
    nb_lignes: int = 0
    nb_valides: int = 0
    nb_erreurs: int = 0
    nb_doublons: int = 0
    nb_ignorees: int = 0
    total_debit: Decimal = Decimal("0.00")
    total_credit: Decimal = Decimal("0.00")
    periode_debut: date | None = None
    periode_fin: date | None = None
    par_compte: list[AccountTotal] = field(default_factory=list)


@dataclass
class AccountingAnalysis:
    company: Company
    fichier_nom: str
    fichier_hash: str
    deja_importe: bool
    feuilles: list[str]
    feuille: str
    ligne_entete: int
    colonnes: list[Column]
    mapping: Mapping
    mapping_source: str  # Détection / Modèle de la société / Utilisateur
    erreurs_mapping: list[str]
    lignes: list[EntryLine] = field(default_factory=list)
    resume: EntriesSummary = field(default_factory=EntriesSummary)


def _company(db: Session, company_id: int) -> Company:
    company = account_repository.get_company(db, company_id)
    if company is None or not company.actif:
        raise NotFoundError("Société introuvable.")
    return company


def _code(value: object) -> str:
    """Journal ou compte lu dans une cellule : texte en majuscules, sans espaces ; un nombre lu par
    Excel (514100, 514100.0) redevient son texte entier."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return "".join((clean_text(value) or "").split()).upper()


def _is_ignored(cells: dict[str, object]) -> bool:
    """Ligne de titre ou de total : ni date ni montant."""
    amounts = ("debit", "credit", "montant")
    return is_blank(cells.get("date_ecriture")) and all(is_blank(cells.get(c)) for c in amounts)


def _bank_account_of(cells: dict[str, object], journals: dict[str, BankAccount]) -> BankAccount | None:
    """Compte bancaire de la ligne, ou None si elle n'est pas une ligne banque d'un journal de banque."""
    account = journals.get(_code(cells.get("journal")))
    if account is None:
        return None
    if account.compte_comptable and not _code(cells.get("compte")).startswith(account.compte_comptable):
        return None  # contrepartie (411, 441, 6147...)
    return account


def _read_entry(
    numero: int, cells: dict[str, object], mapping: Mapping, account: BankAccount, today: date
) -> EntryLine:
    line = EntryLine(numero=numero, statut="Valide", motifs=[])
    line.journal = _code(cells.get("journal"))[:JOURNAL_MAX]
    line.compte = _code(cells.get("compte"))[:COMPTE_MAX]
    line.bank_account_id, line.bank_code = account.id, account.bank.code

    def amount(code: str) -> Decimal | None:
        try:
            return parse_amount(cells.get(code))
        except ValueError as error:
            line.motifs.append(f"{FIELD_LABELS[code]} : {error}")
            return None

    try:
        line.date_ecriture = parse_date(cells.get("date_ecriture"))
        if line.date_ecriture is None:
            line.motifs.append("Date manquante.")
        elif line.date_ecriture > today:
            line.motifs.append("Date dans le futur.")
    except ValueError as error:
        line.motifs.append(f"Date : {error}")
    try:
        line.echeance = parse_date(cells.get("echeance"))
    except ValueError as error:
        line.motifs.append(f"Échéance : {error}")

    line.libelle = clean_libelle(cells.get("libelle"))
    if line.libelle is None:
        line.motifs.append("Libellé manquant.")

    unreadable = len(line.motifs)
    if mapping.get("montant") is not None:
        signed = amount("montant")
        if signed:
            line.credit = max(signed, Decimal("0.00"))
            line.debit = max(-signed, Decimal("0.00"))
        elif len(line.motifs) == unreadable:
            line.motifs.append("Montant manquant ou nul.")
    else:
        debit, credit = amount("debit"), amount("credit")
        if len(line.motifs) == unreadable:
            debit = abs(debit) if debit is not None else Decimal("0.00")
            credit = abs(credit) if credit is not None else Decimal("0.00")
            if debit and credit:
                line.motifs.append("Débit et crédit renseignés sur la même ligne.")
            elif not debit and not credit:
                line.motifs.append("Montant manquant ou nul.")
            else:
                line.debit, line.credit = debit, credit
    if line.debit is not None and line.credit is not None:
        line.montant = line.credit - line.debit

    reference = clean_text(cells.get("reference"))
    line.reference = reference[:REFERENCE_MAX] if reference else None
    line.numero_piece = clean_text(cells.get("numero_piece"))
    if line.numero_piece and len(line.numero_piece) > PIECE_MAX:
        line.motifs.append(f"N° pièce : {PIECE_MAX} caractères au plus.")
    line.tiers = clean_text(cells.get("tiers"))
    if line.tiers and len(line.tiers) > TIERS_MAX:
        line.motifs.append(f"Tiers : {TIERS_MAX} caractères au plus.")

    if line.motifs:
        line.statut = "Erreur"
    return line


def _line_key(line: EntryLine) -> tuple:
    return (
        line.date_ecriture,
        line.journal,
        line.compte,
        line.libelle,
        line.debit,
        line.credit,
        line.numero_piece,
        line.reference,
    )


def _mark_duplicates(db: Session, company_id: int, lines: list[EntryLine]) -> None:
    first_seen: dict[tuple, int] = {}
    occurrences: Counter[tuple] = Counter()
    for line in lines:
        if line.statut != "Valide":
            continue
        key = _line_key(line)
        occurrences[key] += 1
        line.hash_ligne = line_hash(company_id, key, occurrences[key])
        if key in first_seen:
            line.statut = "Doublon"
            line.doublon_de = first_seen[key]
            line.motifs.append(f"Ligne identique à la ligne {first_seen[key]} du fichier.")
        else:
            first_seen[key] = line.numero
    hashes = [line.hash_ligne for line in lines if line.hash_ligne]
    known = accounting_repository.existing_entry_hashes(db, company_id, hashes)
    for line in lines:
        if line.hash_ligne in known:
            line.statut = "Doublon"
            line.doublon_de = None
            line.motifs = ["Déjà importée pour cette société."]


def _summarise(lines: list[EntryLine], ignored: int) -> EntriesSummary:
    summary = EntriesSummary(nb_lignes=len(lines), nb_ignorees=ignored)
    valid = [line for line in lines if line.statut == "Valide"]
    summary.nb_valides = len(valid)
    summary.nb_erreurs = sum(1 for line in lines if line.statut == "Erreur")
    summary.nb_doublons = sum(1 for line in lines if line.statut == "Doublon")
    summary.total_debit = sum((line.debit for line in valid), Decimal("0.00"))
    summary.total_credit = sum((line.credit for line in valid), Decimal("0.00"))
    if valid:
        dates = [line.date_ecriture for line in valid]
        summary.periode_debut, summary.periode_fin = min(dates), max(dates)
    totals: dict[int, AccountTotal] = {}
    for line in valid:
        total = totals.setdefault(
            line.bank_account_id, AccountTotal(line.bank_account_id, line.bank_code)
        )
        total.nb += 1
        total.total_debit += line.debit
        total.total_credit += line.credit
    summary.par_compte = sorted(totals.values(), key=lambda item: item.bank_code)
    return summary


def analyse_entries(
    db: Session,
    *,
    company_id: int,
    fichier_nom: str,
    content: bytes,
    mapping: Mapping | None = None,
    feuille: str | None = None,
    today: date | None = None,
) -> AccountingAnalysis:
    """Analyse un export Sage pour une société. Ne modifie pas la base."""
    company = _company(db, company_id)
    journals = {
        account.journal_sage: account
        for account in accounting_repository.bank_journals(db, company.id)
    }
    if not journals:
        raise ConflictError("Renseignez le journal Sage de vos comptes bancaires (écran Comptes).")
    import_file.check_file(fichier_nom, content)
    feuilles, feuille, rows = import_file.read_sheet(content, feuille)
    header_index = import_file.detect_header(rows, ACCOUNTING_FIELDS)
    data = rows[header_index + 1 :]
    if len(data) > import_file.MAX_ROWS:
        raise ConflictError(f"Fichier trop long : {import_file.MAX_ROWS} lignes au plus par fichier.")
    columns = import_file.columns_of(rows[header_index], data)

    if mapping is not None:
        source = "Utilisateur"
        mapping = {item.code: mapping.get(item.code) for item in ACCOUNTING_FIELDS}
    else:
        saved = accounting_repository.latest_company_mapping(db, company.id, TYPE_IMPORT)
        found = (
            import_file.mapping_from_headers(saved.mapping, columns, ACCOUNTING_FIELDS)
            if saved
            else None
        )
        source = "Modèle de la société" if found else "Détection"
        mapping = found or import_file.propose_mapping(columns, ACCOUNTING_FIELDS)

    fhash = file_hash(content)
    analysis = AccountingAnalysis(
        company=company,
        fichier_nom=fichier_nom,
        fichier_hash=fhash,
        deja_importe=import_repository.confirmed_file(db, company.id, TYPE_IMPORT, fhash)
        is not None,
        feuilles=feuilles,
        feuille=feuille,
        ligne_entete=header_index + 1,
        colonnes=columns,
        mapping=mapping,
        mapping_source=source,
        erreurs_mapping=import_file.mapping_errors(mapping, len(columns), ACCOUNTING_FIELDS),
    )
    if analysis.erreurs_mapping:
        return analysis

    today = today or position_service.business_today()
    lines, ignored = [], 0
    for offset, row in enumerate(data):
        if all(is_blank(cell) for cell in row):
            continue
        cells = {
            code: row[index] if index < len(row) else None
            for code, index in mapping.items()
            if index is not None
        }
        account = None if _is_ignored(cells) else _bank_account_of(cells, journals)
        if account is None:
            ignored += 1
            continue
        lines.append(_read_entry(header_index + 2 + offset, cells, mapping, account, today))

    _mark_duplicates(db, company.id, lines)
    analysis.lignes = lines
    analysis.resume = _summarise(lines, ignored)
    return analysis
```

- [ ] **Step 5 : schémas `backend/app/schemas/accounting.py` (partie analyse)**

```python
"""Import et lecture des écritures comptables (P10). Montants en texte exact."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel

from app.schemas.statement import ChampOut, ColonneOut
from app.services.accounting_import_service import ACCOUNTING_FIELDS, AccountingAnalysis

AccountingFieldCode = Literal[
    "date_ecriture", "journal", "compte", "libelle", "reference", "debit", "credit",
    "montant", "numero_piece", "echeance", "tiers",
]
ColumnIndex = Annotated[int, Field(ge=0, le=16383)]


class MappingComptableIn(RootModel[dict[AccountingFieldCode, ColumnIndex | None]]):
    """Correspondance choisie : champ → index de colonne (0 = colonne A)."""


class LigneComptableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    numero: int
    statut: Literal["Valide", "Erreur", "Doublon"]
    motifs: list[str]
    date_ecriture: date | None
    journal: str | None
    compte: str | None
    libelle: str | None
    reference: str | None
    debit: Decimal | None
    credit: Decimal | None
    montant: Decimal | None
    numero_piece: str | None
    echeance: date | None
    tiers: str | None
    bank_account_id: int | None
    bank_code: str | None
    hash_ligne: str | None
    doublon_de: int | None


class TotalCompteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    bank_account_id: int
    bank_code: str
    nb: int
    total_debit: Decimal
    total_credit: Decimal


class ResumeComptableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    nb_lignes: int
    nb_valides: int
    nb_erreurs: int
    nb_doublons: int
    nb_ignorees: int
    total_debit: Decimal
    total_credit: Decimal
    periode_debut: date | None
    periode_fin: date | None
    par_compte: list[TotalCompteOut]


class AnalyseComptableOut(BaseModel):
    """Aperçu d'un export Sage : rien n'est encore enregistré."""

    company_id: int
    fichier_nom: str
    fichier_hash: str
    deja_importe: bool
    feuilles: list[str]
    feuille: str
    ligne_entete: int
    colonnes: list[ColonneOut]
    champs: list[ChampOut]
    mapping: dict[str, int | None]
    mapping_source: Literal["Détection", "Modèle de la société", "Utilisateur"]
    erreurs_mapping: list[str]
    lignes: list[LigneComptableOut]
    resume: ResumeComptableOut

    @classmethod
    def from_analysis(cls, analysis: AccountingAnalysis) -> "AnalyseComptableOut":
        return cls(
            company_id=analysis.company.id,
            fichier_nom=analysis.fichier_nom,
            fichier_hash=analysis.fichier_hash,
            deja_importe=analysis.deja_importe,
            feuilles=analysis.feuilles,
            feuille=analysis.feuille,
            ligne_entete=analysis.ligne_entete,
            colonnes=[ColonneOut.model_validate(column) for column in analysis.colonnes],
            champs=[
                ChampOut(code=item.code, libelle=item.libelle, obligatoire=item.obligatoire)
                for item in ACCOUNTING_FIELDS
            ],
            mapping=analysis.mapping,
            mapping_source=analysis.mapping_source,
            erreurs_mapping=analysis.erreurs_mapping,
            lignes=[LigneComptableOut.model_validate(line) for line in analysis.lignes],
            resume=ResumeComptableOut.model_validate(analysis.resume),
        )
```

- [ ] **Step 6 : routeur `backend/app/api/accounting.py` (analyse) et enregistrement**

```python
"""Import et lecture des écritures comptables Sage / SI (P10)."""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.deps import require_any_permission, require_permission
from app.core.db import get_db
from app.core.permissions import PermissionCode
from app.schemas.accounting import AnalyseComptableOut, MappingComptableIn
from app.services import accounting_import_service, import_file
from app.services.auth_service import CurrentUser

router = APIRouter(prefix="/accounting", tags=["accounting"])

can_import = require_permission(PermissionCode.ACCOUNTING_IMPORT)
can_read = require_any_permission(PermissionCode.ACCOUNTING_IMPORT, PermissionCode.RECONCILIATION_VIEW)

Fichier = Annotated[UploadFile, File(description="Export Sage / SI au format .xlsx")]
SocieteId = Annotated[int, Form(description="Société de l'export")]
MappingForm = Annotated[str | None, Form(description="JSON {champ: index de colonne}")]
FeuilleForm = Annotated[str | None, Form(description="Feuille du classeur à lire")]


def _content(fichier: UploadFile) -> bytes:
    return fichier.file.read(import_file.MAX_FILE_BYTES + 1)


def _mapping(raw: str | None) -> dict[str, int | None] | None:
    if raw is None or not raw.strip():
        return None
    try:
        return MappingComptableIn.model_validate(json.loads(raw)).root
    except (ValueError, ValidationError) as error:
        raise RequestValidationError(
            [{"type": "value_error", "loc": ("body", "mapping"), "msg": "Correspondance illisible.", "input": None}]
        ) from error


@router.post("/import/analyse", response_model=AnalyseComptableOut)
def analyse_entries(
    fichier: Fichier,
    company_id: SocieteId,
    mapping: MappingForm = None,
    feuille: FeuilleForm = None,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_import),
) -> AnalyseComptableOut:
    """Analyse un export Sage et renvoie son aperçu. Rien n'est enregistré."""
    analysis = accounting_import_service.analyse_entries(
        db,
        company_id=company_id,
        fichier_nom=fichier.filename or "",
        content=_content(fichier),
        mapping=_mapping(mapping),
        feuille=feuille or None,
    )
    return AnalyseComptableOut.from_analysis(analysis)
```

Vérifier le nom exact de `require_any_permission` dans `backend/app/api/deps.py` (déjà utilisé par `statements.py`) et sa signature (arguments variadiques ou liste) ; l'appeler de la même façon que `statements.py`. Dans `backend/app/api/router.py`, importer `accounting` et l'ajouter à `protected_router` comme les autres modules.

- [ ] **Step 7 : vérifier**

Run : `docker compose run --rm backend pytest tests/test_accounting_import_api.py tests/test_permissions.py -q` ; `ruff check .` ; `ruff format --check .`
Expected : tous les tests de l'analyse passent (ceux de la confirmation, tâche 4, ne sont pas encore écrits).

- [ ] **Step 8 : ne pas commiter.**

---

### Task 4 : confirmation d'un import Sage

**Files :**
- Modify : `backend/app/services/accounting_import_service.py`, `backend/app/schemas/accounting.py`, `backend/app/api/accounting.py`
- Test : `backend/tests/test_accounting_import_api.py`

**Interfaces :**
- Consumes : `analyse_entries`, `EntryLine`, `accounting_repository.add / latest_company_mapping`, `import_file.headers_of`, `audit_service.log`.
- Produces : `@dataclass EntriesImport(batch: ImportBatch, nb_importees: int, nb_erreurs_ecartees: int, nb_doublons_ecartes: int, par_compte: list[AccountTotal], periode_debut, periode_fin, modele_enregistre: bool)` ; `confirm_entries(db, *, company_id, fichier_nom, content, mapping, feuille, garder_doublons: list[int] | None, ecarter_erreurs: bool, acteur_id: int, ip: str | None = None, today: date | None = None) -> EntriesImport` ; `POST /api/accounting/import/confirm` → `ConfirmationComptableOut` (201).

- [ ] **Step 1 : tests (à la fin de `test_accounting_import_api.py`)**

```python
def confirm(client, headers, db, content, **form):
    return post(client, CONFIRM, headers, db, content, **form)


def test_confirmed_export_saves_the_bank_lines(client, comptable, db, journals):
    awb, bp = journals

    response = confirm(client, comptable, db, xlsx(EXPORT))

    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["nb_importees"], body["nb_erreurs_ecartees"], body["nb_doublons_ecartes"]) == (2, 0, 0)
    entries = db.scalars(select(AccountingEntry).order_by(AccountingEntry.id)).all()
    assert [(e.bank_account_id, e.journal, e.debit, e.credit, e.montant, e.statut) for e in entries] == [
        (awb.id, "BQ1", Decimal("38500.00"), Decimal("0.00"), Decimal("-38500.00"), "Non rapprochée"),
        (bp.id, "BQ2", Decimal("0.00"), Decimal("12800.00"), Decimal("12800.00"), "Non rapprochée"),
    ]
    batch = db.get(ImportBatch, body["import_id"])
    assert (batch.type, batch.statut, batch.nb_lignes, batch.company_id) == (
        "Comptabilité", "Confirmé", 2, company(db).id,
    )
    [entry] = db.scalars(select(AuditLog).filter_by(action="import_ecritures")).all()
    assert entry.nouvelle_valeur["fichier"] == "export.xlsx"
    assert entry.nouvelle_valeur["ecritures"] == 2


def test_mapping_is_remembered_for_the_company(client, comptable, db, journals):
    rows = [["Dt", "Jnl", "Cpt", "Lib", "Mnt"], [date(2025, 9, 2), "BQ1", "5141", "VIR", 10]]
    mapping = {"date_ecriture": 0, "journal": 1, "compte": 2, "libelle": 3, "montant": 4}
    confirm(client, comptable, db, xlsx(rows), mapping=mapping)

    rows[1][3] = "AUTRE VIR"
    body = analyse(client, comptable, db, xlsx(rows), nom="export2.xlsx").json()

    assert body["mapping_source"] == "Modèle de la société"
    assert body["lignes"][0]["statut"] == "Valide"
    saved = db.scalar(select(ColumnMapping).filter_by(type="Comptabilité"))
    assert (saved.company_id, saved.bank_id) == (company(db).id, None)


def test_errors_block_the_confirmation_unless_discarded(client, comptable, db, journals):
    bad = [date(2025, 9, 4), "BQ1", "5141", "P9", None, 5, None, None, None]
    content = xlsx([*EXPORT, bad])

    refused = confirm(client, comptable, db, content)
    accepted = confirm(client, comptable, db, content, ecarter_erreurs="true")

    assert refused.status_code == 409
    assert refused.json() == {"detail": "1 ligne en erreur : corrigez l'export dans Sage, ou confirmez en l'écartant."}
    assert accepted.status_code == 201
    assert accepted.json()["nb_erreurs_ecartees"] == 1


def test_same_file_cannot_be_imported_twice(client, comptable, db, journals):
    confirm(client, comptable, db, xlsx(EXPORT))

    again = confirm(client, comptable, db, xlsx(EXPORT))

    assert again.status_code == 409
    assert again.json() == {"detail": "Ce fichier a déjà été importé pour cette société."}


def test_lines_already_imported_are_skipped_in_a_new_file(client, comptable, db, journals):
    confirm(client, comptable, db, xlsx(EXPORT))
    newer = [*EXPORT, [date(2025, 9, 5), "BQ1", "5141", "P003", "FRAIS", 50, None, None, None]]

    body = confirm(client, comptable, db, xlsx(newer)).json()

    assert (body["nb_importees"], body["nb_doublons_ecartes"]) == (1, 2)


def test_internal_duplicate_can_be_kept(client, comptable, db, journals):
    row = [date(2025, 9, 2), "BQ1", "5141", "P1", "FRAIS", 10, None, None, None]

    body = confirm(client, comptable, db, xlsx([HEADER, row, row]), garder_doublons="[3]").json()

    assert body["nb_importees"] == 2


def test_file_without_bank_line_is_refused(client, comptable, db, journals):
    response = confirm(client, comptable, db, xlsx(EXPORT[:2] + EXPORT[5:]))

    assert response.status_code == 409
    assert response.json() == {"detail": "Aucune écriture de banque à importer dans ce fichier."}
```

- [ ] **Step 2 : vérifier l'échec** — Run : `docker compose run --rm backend pytest tests/test_accounting_import_api.py -q -k "confirm or remembered or twice or kept or skipped or blocked or refused"` ; Expected : 404 / 405 sur `/import/confirm`.

- [ ] **Step 3 : service (à la fin de `accounting_import_service.py`)**

```python
from sqlalchemy.exc import IntegrityError

from app.models import AccountingEntry, ColumnMapping, ImportBatch
from app.services import audit_service


@dataclass
class EntriesImport:
    batch: ImportBatch
    nb_importees: int
    nb_erreurs_ecartees: int
    nb_doublons_ecartes: int
    par_compte: list[AccountTotal]
    periode_debut: date | None
    periode_fin: date | None
    modele_enregistre: bool


def _save_mapping(db: Session, company: Company, analysis: AccountingAnalysis) -> bool:
    headers = import_file.headers_of(analysis.mapping, analysis.colonnes)
    if headers is None:
        return False
    saved = accounting_repository.latest_company_mapping(db, company.id, TYPE_IMPORT)
    if saved is None:
        accounting_repository.add(
            db,
            ColumnMapping(type=TYPE_IMPORT, company_id=company.id, nom=f"Export Sage {company.nom}", mapping=headers),
        )
    else:
        saved.mapping = headers
    return True


def confirm_entries(
    db: Session,
    *,
    company_id: int,
    fichier_nom: str,
    content: bytes,
    mapping: Mapping | None,
    feuille: str | None,
    garder_doublons: list[int] | None,
    ecarter_erreurs: bool,
    acteur_id: int,
    ip: str | None = None,
    today: date | None = None,
) -> EntriesImport:
    """Enregistre l'export : le fichier est analysé à nouveau (sans état entre les deux temps)."""
    analysis = analyse_entries(
        db, company_id=company_id, fichier_nom=fichier_nom, content=content,
        mapping=mapping, feuille=feuille, today=today,
    )
    if analysis.erreurs_mapping:
        raise ConflictError(" ".join(analysis.erreurs_mapping))
    if analysis.deja_importe:
        raise ConflictError("Ce fichier a déjà été importé pour cette société.")
    errors = [line for line in analysis.lignes if line.statut == "Erreur"]
    if errors and not ecarter_erreurs:
        plural = "s" if len(errors) > 1 else ""
        raise ConflictError(
            f"{len(errors)} ligne{plural} en erreur : corrigez l'export dans Sage, "
            f"ou confirmez en l'écartant{plural}."
        )
    keep = set(garder_doublons or [])
    by_number = {line.numero: line for line in analysis.lignes}
    for numero in sorted(keep):
        line = by_number.get(numero)
        if line is None or line.doublon_de is None:
            raise ConflictError(
                f"La ligne {numero} n'est pas identique à une autre ligne du fichier : "
                "elle ne peut pas être gardée."
            )
    lines = [line for line in analysis.lignes if line.statut == "Valide" or line.numero in keep]
    if not lines:
        raise ConflictError("Aucune écriture de banque à importer dans ce fichier.")

    company = analysis.company
    batch = ImportBatch(
        type=TYPE_IMPORT,
        company_id=company.id,
        fichier_nom=fichier_nom,
        fichier_hash=analysis.fichier_hash,
        statut="Confirmé",
        nb_lignes=len(lines),
        nb_erreurs=len(errors),
        nb_doublons=sum(1 for line in analysis.lignes if line.statut == "Doublon") - len(keep),
        user_id=acteur_id,
    )
    accounting_repository.add(db, batch)
    db.flush()
    for line in lines:
        accounting_repository.add(
            db,
            AccountingEntry(
                import_batch_id=batch.id,
                company_id=company.id,
                bank_account_id=line.bank_account_id,
                journal=line.journal,
                compte=line.compte,
                date_ecriture=line.date_ecriture,
                libelle=line.libelle,
                reference=line.reference,
                debit=line.debit,
                credit=line.credit,
                montant=line.montant,
                numero_piece=line.numero_piece,
                echeance=line.echeance,
                tiers=line.tiers,
                hash_ligne=line.hash_ligne,
            ),
        )
    modele = _save_mapping(db, company, analysis)
    summary = _summarise([*lines], 0)
    audit_service.log(
        db,
        user_id=acteur_id,
        action="import_ecritures",
        entite="import_batch",
        entite_id=batch.id,
        apres={
            "fichier": fichier_nom,
            "ecritures": len(lines),
            "par_compte": {item.bank_code: item.nb for item in summary.par_compte},
            "erreurs_ecartees": len(errors),
            "doublons_gardes": sorted(keep),
        },
        ip=ip,
    )
    try:
        db.commit()
    except IntegrityError as error:  # même fichier confirmé en même temps
        db.rollback()
        raise ConflictError("Ce fichier a déjà été importé pour cette société.") from error
    return EntriesImport(
        batch=batch,
        nb_importees=len(lines),
        nb_erreurs_ecartees=len(errors),
        nb_doublons_ecartes=batch.nb_doublons,
        par_compte=summary.par_compte,
        periode_debut=summary.periode_debut,
        periode_fin=summary.periode_fin,
        modele_enregistre=modele,
    )
```

Note : pour un doublon gardé, `line.hash_ligne` est déjà distinct (occurrence 2). `_summarise` doit accepter des lignes « Doublon » gardées : remplacer `valid = [... statut == "Valide"]` par un paramètre ; plus simple : avant `_summarise`, construire une copie `dataclasses.replace(line, statut="Valide")` des lignes gardées. Écrire `summary = _summarise([replace(line, statut="Valide") for line in lines], 0)` (importer `replace` de `dataclasses`).

- [ ] **Step 4 : schéma et route**

`schemas/accounting.py` :

```python
class ConfirmationComptableOut(BaseModel):
    import_id: int
    fichier_nom: str
    nb_importees: int
    nb_erreurs_ecartees: int
    nb_doublons_ecartes: int
    par_compte: list[TotalCompteOut]
    periode_debut: date | None
    periode_fin: date | None
    modele_enregistre: bool

    @classmethod
    def from_import(cls, result) -> "ConfirmationComptableOut":
        return cls(
            import_id=result.batch.id,
            fichier_nom=result.batch.fichier_nom,
            nb_importees=result.nb_importees,
            nb_erreurs_ecartees=result.nb_erreurs_ecartees,
            nb_doublons_ecartes=result.nb_doublons_ecartes,
            par_compte=[TotalCompteOut.model_validate(item) for item in result.par_compte],
            periode_debut=result.periode_debut,
            periode_fin=result.periode_fin,
            modele_enregistre=result.modele_enregistre,
        )


class LignesGardeesIn(RootModel[list[Annotated[int, Field(ge=1)]]]):
    """Numéros des doublons internes à garder."""
```

`api/accounting.py` :

```python
@router.post("/import/confirm", response_model=ConfirmationComptableOut, status_code=201)
def confirm_entries(
    request: Request,
    fichier: Fichier,
    company_id: SocieteId,
    mapping: MappingForm = None,
    feuille: FeuilleForm = None,
    garder_doublons: Annotated[str | None, Form(description="JSON [numéros de ligne]")] = None,
    ecarter_erreurs: Annotated[bool, Form()] = False,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_import),
) -> ConfirmationComptableOut:
    """Enregistre l'export (même fichier, même correspondance que l'aperçu)."""
    kept = None
    if garder_doublons:
        try:
            kept = LignesGardeesIn.model_validate(json.loads(garder_doublons)).root
        except (ValueError, ValidationError) as error:
            raise RequestValidationError(
                [{"type": "value_error", "loc": ("body", "garder_doublons"), "msg": "Liste de lignes illisible.", "input": None}]
            ) from error
    result = accounting_import_service.confirm_entries(
        db,
        company_id=company_id,
        fichier_nom=fichier.filename or "",
        content=_content(fichier),
        mapping=_mapping(mapping),
        feuille=feuille or None,
        garder_doublons=kept,
        ecarter_erreurs=ecarter_erreurs,
        acteur_id=user.id,
        ip=client_ip(request),
    )
    return ConfirmationComptableOut.from_import(result)
```

(importer `Request` de fastapi et `client_ip` de `app.api.deps`).

- [ ] **Step 5 : vérifier** — Run : `docker compose run --rm backend pytest tests/test_accounting_import_api.py -q` ; Expected : tout passe. Puis `ruff check .`, `ruff format --check .`.

- [ ] **Step 6 : ne pas commiter.**

---

### Task 5 : lecture des écritures et journal des imports

**Files :**
- Modify : `backend/app/repositories/accounting_repository.py`, `backend/app/services/accounting_import_service.py`, `backend/app/schemas/accounting.py`, `backend/app/api/accounting.py`
- Test : `backend/tests/test_accounting_entries_api.py` (créer)

**Interfaces :**
- Produces : `PAGE_SIZE = 50` ; `EntriesPage(total, page, taille, total_debit, total_credit, ecritures: list[tuple[AccountingEntry, str]])` ; `list_entries(db, company_id, *, bank_account_id=None, date_from=None, date_to=None, statut=None, q=None, page=1) -> EntriesPage` ; `get_entry(db, entry_id) -> EntryDetail` ; `list_imports(db, company_id) -> list[ImportSummary]` ; routes `GET /api/accounting/entries`, `/entries/{id}`, `/imports`.

- [ ] **Step 1 : tests** — créer `backend/tests/test_accounting_entries_api.py` :

```python
"""Lecture des écritures comptables importées (P10)."""

from datetime import date
from decimal import Decimal
from itertools import count

import pytest
from sqlalchemy import select

from app.models import AccountingEntry, Bank, BankAccount, Company, ImportBatch, User
from tests.helpers import bearer, build_account, login, make_auth_user, save

URL = "/api/accounting/entries"
_seq = count(1)


@pytest.fixture
def direction(client, reference) -> dict[str, str]:
    make_auth_user(reference, "DIRECTION", email="direction@example.com")
    return bearer(login(client, "direction@example.com"))


def company(db, code="SIMTIS") -> Company:
    return db.scalar(select(Company).filter_by(code=code))


def account(db, bank_code="AWB", company_code="SIMTIS") -> BankAccount:
    bank = db.scalar(select(Bank).filter_by(code=bank_code))
    return save(db, build_account(company(db, company_code), bank, numero=f"RIB-ENT-{next(_seq):06d}"))


def entry(db, compte: BankAccount, jour: date, libelle="VIR", debit="0", credit="10", **over) -> AccountingEntry:
    debit, credit = Decimal(debit), Decimal(credit)
    return save(
        db,
        AccountingEntry(
            company_id=compte.company_id,
            bank_account_id=compte.id,
            journal="BQ1",
            compte="5141",
            date_ecriture=jour,
            libelle=libelle,
            debit=debit,
            credit=credit,
            montant=credit - debit,
            hash_ligne=f"h{next(_seq)}",
            **over,
        ),
    )


def get(client, headers, db, code="SIMTIS", **params):
    return client.get(URL, params={"company_id": str(company(db, code).id), **params}, headers=headers)


def test_entries_are_listed_newest_first_with_totals(client, direction, db):
    awb = account(db)
    entry(db, awb, date(2025, 9, 1), credit="10")
    entry(db, awb, date(2025, 9, 3), debit="4", credit="0")

    body = get(client, direction, db).json()

    assert (body["total"], body["page"], body["taille"]) == (2, 1, 50)
    assert [item["date_ecriture"] for item in body["ecritures"]] == ["2025-09-03", "2025-09-01"]
    assert (body["total_debit"], body["total_credit"]) == ("4.00", "10.00")
    assert body["ecritures"][0]["bank_code"] == "AWB"


def test_filters_by_account_dates_and_status(client, direction, db):
    awb, bp = account(db, "AWB"), account(db, "BP")
    entry(db, awb, date(2025, 9, 1))
    entry(db, bp, date(2025, 9, 2))
    entry(db, bp, date(2025, 9, 20), statut="Rapprochée")

    by_account = get(client, direction, db, bank_account_id=str(bp.id)).json()
    by_dates = get(client, direction, db, **{"from": "2025-09-02", "to": "2025-09-10"}).json()
    by_status = get(client, direction, db, statut="Rapprochée").json()

    assert by_account["total"] == 2
    assert by_dates["total"] == 1
    assert by_status["total"] == 1


def test_search_looks_in_label_piece_reference_and_third_party(client, direction, db):
    awb = account(db)
    entry(db, awb, date(2025, 9, 1), libelle="REG CLIENT ATLAS")
    entry(db, awb, date(2025, 9, 2), numero_piece="P-778")
    entry(db, awb, date(2025, 9, 3), tiers="Atlas Textile")

    assert get(client, direction, db, q="atlas").json()["total"] == 2
    assert get(client, direction, db, q="p-778").json()["total"] == 1


def test_search_treats_like_wildcards_as_text(client, direction, db):
    awb = account(db)
    entry(db, awb, date(2025, 9, 1), libelle="REMISE 100%")
    entry(db, awb, date(2025, 9, 2), libelle="AUTRE")

    assert get(client, direction, db, q="%").json()["total"] == 1
    assert get(client, direction, db, q="_").json()["total"] == 0


def test_pagination_by_fifty(client, direction, db):
    awb = account(db)
    for day in range(1, 31):
        entry(db, awb, date(2025, 8, day))
        entry(db, awb, date(2025, 9, day))

    page2 = get(client, direction, db, page="2").json()

    assert (page2["total"], len(page2["ecritures"])) == (60, 10)
    assert page2["total_credit"] == "600.00"  # totaux sur tout le filtre


def test_page_beyond_the_last_is_empty(client, direction, db):
    entry(db, account(db), date(2025, 9, 1))

    body = get(client, direction, db, page="9").json()

    assert (body["total"], body["ecritures"]) == (1, [])


def test_other_company_entries_are_never_listed(client, direction, db):
    entry(db, account(db, "AWB", "SOCX"), date(2025, 9, 1))

    assert get(client, direction, db).json()["total"] == 0


def test_entry_detail_names_its_import(client, direction, db, reference):
    author = db.scalar(select(User).filter_by(email="direction@example.com"))
    batch = save(db, ImportBatch(type="Comptabilité", company_id=company(db).id, fichier_nom="sage.xlsx",
                                 fichier_hash="x" * 64, statut="Confirmé", user_id=author.id))
    item = entry(db, account(db), date(2025, 9, 1), import_batch_id=batch.id)

    body = client.get(f"{URL}/{item.id}", headers=direction).json()

    assert (body["fichier_nom"], body["importe_par"]) == ("sage.xlsx", author.nom)


def test_imports_journal(client, direction, db):
    batch = save(db, ImportBatch(type="Comptabilité", company_id=company(db).id, fichier_nom="sage.xlsx",
                                 fichier_hash="y" * 64, statut="Confirmé", nb_lignes=2))
    awb = account(db)
    entry(db, awb, date(2025, 9, 1), import_batch_id=batch.id, credit="10")
    entry(db, awb, date(2025, 9, 4), import_batch_id=batch.id, debit="3", credit="0")

    [row] = client.get("/api/accounting/imports", params={"company_id": str(company(db).id)}, headers=direction).json()

    assert row | {"id": 0, "importe_le": None} == {
        "id": 0,
        "importe_le": None,
        "importe_par": None,
        "fichier_nom": "sage.xlsx",
        "periode_debut": "2025-09-01",
        "periode_fin": "2025-09-04",
        "nb_ecritures": 2,
        "total_debit": "3.00",
        "total_credit": "10.00",
    }


def test_unknown_entry_gives_404(client, direction):
    assert client.get(f"{URL}/999999", headers=direction).status_code == 404


def test_requires_a_token(client, reference):
    assert client.get(URL, params={"company_id": "1"}).status_code == 401


def test_requires_a_reading_permission(client, reference, db):
    make_auth_user(reference, email="sans-role@example.com")
    headers = bearer(login(client, "sans-role@example.com"))

    assert get(client, headers, db).status_code == 403
```

- [ ] **Step 2 : vérifier l'échec** — 404 sur les routes.

- [ ] **Step 3 : dépôt** (`accounting_repository.py`, ajouter) :

```python
from datetime import date

from sqlalchemy import func, or_

from app.models import Bank, ImportBatch, User


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def entries_query(company_id, *, bank_account_id=None, date_from=None, date_to=None, statut=None, q=None):
    query = select(AccountingEntry).where(AccountingEntry.company_id == company_id)
    if bank_account_id is not None:
        query = query.where(AccountingEntry.bank_account_id == bank_account_id)
    if date_from is not None:
        query = query.where(AccountingEntry.date_ecriture >= date_from)
    if date_to is not None:
        query = query.where(AccountingEntry.date_ecriture <= date_to)
    if statut is not None:
        query = query.where(AccountingEntry.statut == statut)
    if q:
        pattern = f"%{_escape(q.strip())}%"
        query = query.where(
            or_(*(
                column.ilike(pattern, escape="\\")
                for column in (
                    AccountingEntry.libelle, AccountingEntry.numero_piece,
                    AccountingEntry.reference, AccountingEntry.tiers,
                )
            ))
        )
    return query


def page_of_entries(db: Session, query, *, offset: int, limit: int) -> list[tuple[AccountingEntry, str | None]]:
    filtered = query.subquery()
    rows = db.execute(
        select(AccountingEntry, Bank.code)
        .join(filtered, filtered.c.id == AccountingEntry.id)
        .outerjoin(BankAccount, BankAccount.id == AccountingEntry.bank_account_id)
        .outerjoin(Bank, Bank.id == BankAccount.bank_id)
        .order_by(AccountingEntry.date_ecriture.desc(), AccountingEntry.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return [tuple(row) for row in rows]


def totals_of_entries(db: Session, query) -> tuple[int, Decimal, Decimal]:
    filtered = query.subquery()
    count_, debit, credit = db.execute(
        select(func.count(), func.coalesce(func.sum(filtered.c.debit), 0), func.coalesce(func.sum(filtered.c.credit), 0))
    ).one()
    return count_, Decimal(debit), Decimal(credit)


def get_entry(db: Session, entry_id: int) -> tuple[AccountingEntry, str | None, ImportBatch | None, str | None] | None:
    row = db.execute(
        select(AccountingEntry, Bank.code, ImportBatch, User.nom)
        .outerjoin(BankAccount, BankAccount.id == AccountingEntry.bank_account_id)
        .outerjoin(Bank, Bank.id == BankAccount.bank_id)
        .outerjoin(ImportBatch, ImportBatch.id == AccountingEntry.import_batch_id)
        .outerjoin(User, User.id == ImportBatch.user_id)
        .where(AccountingEntry.id == entry_id)
    ).first()
    return tuple(row) if row else None


def list_imports(db: Session, company_id: int):
    """Imports comptables confirmés de la société, du plus récent au plus ancien, avec leurs totaux."""
    stats = (
        select(
            AccountingEntry.import_batch_id.label("batch_id"),
            func.min(AccountingEntry.date_ecriture).label("debut"),
            func.max(AccountingEntry.date_ecriture).label("fin"),
            func.count().label("nb"),
            func.sum(AccountingEntry.debit).label("debit"),
            func.sum(AccountingEntry.credit).label("credit"),
        )
        .group_by(AccountingEntry.import_batch_id)
        .subquery()
    )
    query = (
        select(ImportBatch, User.nom, stats.c.debut, stats.c.fin, stats.c.nb, stats.c.debit, stats.c.credit)
        .outerjoin(stats, stats.c.batch_id == ImportBatch.id)
        .outerjoin(User, User.id == ImportBatch.user_id)
        .where(ImportBatch.company_id == company_id, ImportBatch.type == "Comptabilité", ImportBatch.statut == "Confirmé")
        .order_by(ImportBatch.created_at.desc(), ImportBatch.id.desc())
    )
    return [tuple(row) for row in db.execute(query)]
```

(importer `Decimal`).

- [ ] **Step 4 : service** (`accounting_import_service.py`, ajouter) :

```python
PAGE_SIZE = 50


@dataclass
class EntriesPage:
    total: int
    page: int
    taille: int
    total_debit: Decimal
    total_credit: Decimal
    ecritures: list[tuple]  # (AccountingEntry, code de la banque)


def list_entries(db, company_id, *, bank_account_id=None, date_from=None, date_to=None, statut=None, q=None, page=1) -> EntriesPage:
    company = _company(db, company_id)
    if date_from and date_to and date_from > date_to:
        raise ConflictError("La date de début doit précéder la date de fin.")
    query = accounting_repository.entries_query(
        company.id, bank_account_id=bank_account_id, date_from=date_from, date_to=date_to, statut=statut, q=q
    )
    total, debit, credit = accounting_repository.totals_of_entries(db, query)
    rows = accounting_repository.page_of_entries(db, query, offset=(page - 1) * PAGE_SIZE, limit=PAGE_SIZE)
    return EntriesPage(total, page, PAGE_SIZE, debit.quantize(Decimal("0.01")), credit.quantize(Decimal("0.01")), rows)


def get_entry(db, entry_id):
    row = accounting_repository.get_entry(db, entry_id)
    if row is None:
        raise NotFoundError("Écriture introuvable.")
    return row


def list_imports(db, company_id):
    _company(db, company_id)
    return accounting_repository.list_imports(db, company_id)
```

- [ ] **Step 5 : schémas et routes**

`schemas/accounting.py` :

```python
class EcritureOut(BaseModel):
    id: int
    date_ecriture: date
    journal: str | None
    compte: str | None
    libelle: str
    reference: str | None
    debit: Decimal
    credit: Decimal
    montant: Decimal
    numero_piece: str | None
    echeance: date | None
    tiers: str | None
    bank_account_id: int | None
    bank_code: str | None
    statut: str

    @classmethod
    def from_row(cls, entry, bank_code) -> "EcritureOut":
        return cls(
            id=entry.id, date_ecriture=entry.date_ecriture, journal=entry.journal, compte=entry.compte,
            libelle=entry.libelle, reference=entry.reference, debit=entry.debit, credit=entry.credit,
            montant=entry.montant, numero_piece=entry.numero_piece, echeance=entry.echeance,
            tiers=entry.tiers, bank_account_id=entry.bank_account_id, bank_code=bank_code, statut=entry.statut,
        )


class EcrituresPageOut(BaseModel):
    total: int
    page: int
    taille: int
    total_debit: Decimal
    total_credit: Decimal
    ecritures: list[EcritureOut]


class EcritureDetailOut(EcritureOut):
    fichier_nom: str | None
    importe_le: datetime | None
    importe_par: str | None


class ImportComptableOut(BaseModel):
    id: int
    importe_le: datetime
    importe_par: str | None
    fichier_nom: str
    periode_debut: date | None
    periode_fin: date | None
    nb_ecritures: int
    total_debit: Decimal
    total_credit: Decimal
```

(importer `datetime`). Pour `ImportComptableOut`, construire à partir du tuple `(batch, nom, debut, fin, nb, debit, credit)` : `nb or 0`, `debit or Decimal("0.00")`, etc.

`api/accounting.py` :

```python
@router.get("/entries", response_model=EcrituresPageOut)
def list_entries(
    company_id: int = Query(),
    bank_account_id: int | None = None,
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    statut: Literal["Non rapprochée", "À vérifier", "Rapprochée", "Écart"] | None = None,
    q: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_read),
) -> EcrituresPageOut:
    result = accounting_import_service.list_entries(
        db, company_id, bank_account_id=bank_account_id, date_from=date_from, date_to=date_to,
        statut=statut, q=q, page=page,
    )
    return EcrituresPageOut(
        total=result.total, page=result.page, taille=result.taille,
        total_debit=result.total_debit, total_credit=result.total_credit,
        ecritures=[EcritureOut.from_row(entry, code) for entry, code in result.ecritures],
    )


@router.get("/entries/{entry_id}", response_model=EcritureDetailOut)
def get_entry(entry_id: int, db: Session = Depends(get_db), _user: CurrentUser = Depends(can_read)) -> EcritureDetailOut:
    entry, code, batch, author = accounting_import_service.get_entry(db, entry_id)
    base = EcritureOut.from_row(entry, code).model_dump()
    return EcritureDetailOut(
        **base, fichier_nom=batch.fichier_nom if batch else None,
        importe_le=batch.created_at if batch else None, importe_par=author,
    )


@router.get("/imports", response_model=list[ImportComptableOut])
def list_imports(company_id: int = Query(), db: Session = Depends(get_db), _user: CurrentUser = Depends(can_read)) -> list[ImportComptableOut]:
    return [
        ImportComptableOut(
            id=batch.id, importe_le=batch.created_at, importe_par=author, fichier_nom=batch.fichier_nom,
            periode_debut=debut, periode_fin=fin, nb_ecritures=nb or 0,
            total_debit=debit or Decimal("0.00"), total_credit=credit or Decimal("0.00"),
        )
        for batch, author, debut, fin, nb, debit, credit in accounting_import_service.list_imports(db, company_id)
    ]
```

Note : `get_entry` lit une écriture de n'importe quelle société ; c'est la même règle que les autres lectures par identifiant du projet (`/api/accounts/{id}`) : la permission de lecture suffit.

- [ ] **Step 6 : vérifier** — `pytest tests/test_accounting_entries_api.py tests/test_accounting_import_api.py -q`, `ruff`, puis la suite complète `pytest -q` et `alembic check`. Expected : tout vert.

- [ ] **Step 7 : ne pas commiter.**

---

### Task 6 : frontend, types, services, règles pures et journal Sage des comptes

**Files :**
- Create : `frontend/types/accounting.ts`, `frontend/services/accounting.ts`, `frontend/lib/accounting.ts`, `frontend/lib/accounting.test.ts`
- Modify : `frontend/types/account.ts`, `frontend/lib/accounts.ts` (+ test), `frontend/components/accounts/AccountFormModal.tsx`, `frontend/components/accounts/AccountsView.tsx`

**Interfaces :**
- Produces : types `LigneComptable`, `AnalyseComptable`, `ConfirmationComptable`, `Ecriture`, `EcrituresPage`, `EcritureDetail`, `ImportComptable`, `EntriesFilter = { bankAccountId?: number; from?: string; to?: string; statut?: string; q?: string; page: number }` ; `entriesQuery(companyId: number, filter: EntriesFilter): string` ; `pageCount(total: number, taille: number): number` ; `accountingForm(file: File, companyId: number, options?: { mapping?: Record<string, number | null>; feuille?: string; garderDoublons?: number[]; ecarterErreurs?: boolean }): FormData` ; services `analyseEntries`, `confirmEntries`, `listEntries`, `getEntry`, `listAccountingImports`. `AccountFormValues.journal_sage: string`.

- [ ] **Step 1 : tests Vitest**

`frontend/lib/accounting.test.ts` :

```ts
import { describe, expect, it } from "vitest";

import { accountingForm, entriesQuery, pageCount } from "./accounting";

describe("entriesQuery", () => {
  it("n'envoie que les filtres renseignés, la page toujours", () => {
    expect(entriesQuery(1, { page: 1 })).toBe("?company_id=1&page=1");
    expect(
      entriesQuery(2, { bankAccountId: 5, from: "2025-09-01", to: "", statut: "Rapprochée", q: " atlas ", page: 3 }),
    ).toBe("?company_id=2&bank_account_id=5&from=2025-09-01&statut=Rapproch%C3%A9e&q=atlas&page=3");
  });
});

describe("pageCount", () => {
  it("compte les pages de 50, au moins une", () => {
    expect(pageCount(0, 50)).toBe(1);
    expect(pageCount(50, 50)).toBe(1);
    expect(pageCount(51, 50)).toBe(2);
  });
});

describe("accountingForm", () => {
  it("joint le fichier, la société et les options de confirmation", () => {
    const file = new File(["x"], "sage.xlsx");

    const form = accountingForm(file, 3, { mapping: { date_ecriture: 0, tiers: null }, garderDoublons: [7, 4], ecarterErreurs: true });

    expect(form.get("company_id")).toBe("3");
    expect(form.get("mapping")).toBe('{"date_ecriture":0}');
    expect(form.get("garder_doublons")).toBe("[4,7]");
    expect(form.get("ecarter_erreurs")).toBe("true");
  });
});
```

Dans `frontend/lib/accounts.test.ts`, ajouter `journal_sage: ""` dans l'objet `valid` et un cas :

```ts
  it("refuse un journal Sage avec un tiret, accepte « bq1 »", () => {
    expect(validateAccountForm({ ...valid, journal_sage: "BQ-1" }, "create").journal_sage).toBeDefined();
    expect(validateAccountForm({ ...valid, journal_sage: "bq1" }, "create")).toEqual({});
  });
```

- [ ] **Step 2 : vérifier l'échec** — `npx vitest run lib/accounting.test.ts lib/accounts.test.ts` ; module absent, `journal_sage` non validé.

- [ ] **Step 3 : code**

`frontend/lib/accounting.ts` :

```ts
/** Import Sage et lecture des écritures (P10) : règles pures, montants en texte exact. */

export type EntriesFilter = {
  bankAccountId?: number;
  from?: string;
  to?: string;
  statut?: string;
  q?: string;
  page: number;
};

export const STATUTS_RAPPROCHEMENT = ["Non rapprochée", "À vérifier", "Rapprochée", "Écart"] as const;

/** « ?company_id=…&… » : seuls les filtres renseignés, la page toujours. */
export function entriesQuery(companyId: number, filter: EntriesFilter): string {
  const params = new URLSearchParams({ company_id: String(companyId) });
  if (filter.bankAccountId !== undefined) params.set("bank_account_id", String(filter.bankAccountId));
  if (filter.from) params.set("from", filter.from);
  if (filter.to) params.set("to", filter.to);
  if (filter.statut) params.set("statut", filter.statut);
  if (filter.q?.trim()) params.set("q", filter.q.trim());
  params.set("page", String(filter.page));
  return `?${params}`;
}

export function pageCount(total: number, taille: number): number {
  return Math.max(1, Math.ceil(total / taille));
}

export function accountingForm(
  file: File,
  companyId: number,
  options: {
    mapping?: Record<string, number | null>;
    feuille?: string;
    garderDoublons?: number[];
    ecarterErreurs?: boolean;
  } = {},
): FormData {
  const form = new FormData();
  form.append("fichier", file);
  form.append("company_id", String(companyId));
  if (options.mapping) {
    const mapped = Object.fromEntries(
      Object.entries(options.mapping).filter(([, index]) => index !== null && index !== undefined),
    );
    form.append("mapping", JSON.stringify(mapped));
  }
  if (options.feuille) form.append("feuille", options.feuille);
  if (options.garderDoublons?.length) {
    form.append("garder_doublons", JSON.stringify([...options.garderDoublons].sort((a, b) => a - b)));
  }
  if (options.ecarterErreurs !== undefined) form.append("ecarter_erreurs", String(options.ecarterErreurs));
  return form;
}
```

`frontend/types/accounting.ts` : un type par schéma de la tâche 3 à 5, montants et dates en `string`, inconnu en `null` (champs identiques aux schémas Pydantic `LigneComptableOut`, `ResumeComptableOut`, `AnalyseComptableOut`, `ConfirmationComptableOut`, `EcritureOut`, `EcrituresPageOut`, `EcritureDetailOut`, `ImportComptableOut`, et `ImportColumn` / `champs` réutilisés depuis `types/statement.ts`).

`frontend/services/accounting.ts` :

```ts
import { apiFetch } from "@/lib/api";
import { accountingForm, entriesQuery, type EntriesFilter } from "@/lib/accounting";
import type { AnalyseComptable, ConfirmationComptable, EcritureDetail, EcrituresPage, ImportComptable } from "@/types/accounting";

type Options = Parameters<typeof accountingForm>[2];

export function analyseEntries(file: File, companyId: number, options?: Options) {
  return apiFetch<AnalyseComptable>("/accounting/import/analyse", { method: "POST", body: accountingForm(file, companyId, options) });
}

export function confirmEntries(file: File, companyId: number, options?: Options) {
  return apiFetch<ConfirmationComptable>("/accounting/import/confirm", { method: "POST", body: accountingForm(file, companyId, options) });
}

export function listEntries(companyId: number, filter: EntriesFilter) {
  return apiFetch<EcrituresPage>(`/accounting/entries${entriesQuery(companyId, filter)}`);
}

export function getEntry(id: number) {
  return apiFetch<EcritureDetail>(`/accounting/entries/${id}`);
}

export function listAccountingImports(companyId: number) {
  return apiFetch<ImportComptable[]>(`/accounting/imports?company_id=${companyId}`);
}
```

Comptes : `types/account.ts` ajoute `journal_sage: string | null` à `Account` et à l'entrée de création / modification ; `lib/accounts.ts` ajoute `journal_sage: string` à `AccountFormValues` et la règle :

```ts
  const journal = values.journal_sage.trim().toUpperCase();
  if (journal && !/^[A-Z0-9]{1,10}$/.test(journal)) {
    errors.journal_sage = "1 à 10 lettres ou chiffres (ex. BQ1).";
  }
```

`AccountFormModal.tsx` : valeur initiale `journal_sage: ""` (création) / `account.journal_sage ?? ""` (modification) ; envoi `journal_sage: values.journal_sage.trim().toUpperCase() || null` ; un `Field` « Journal Sage » (hint « Code du journal de banque dans Sage, ex. BQ1 ») avec un `TextInput` `id="account-journal-sage"`, placé juste après le champ « Compte comptable », sur le même modèle. `AccountsView.tsx` : colonne « Journal Sage » après « Compte comptable » (`row.journal_sage ?? "-"`).

- [ ] **Step 4 : vérifier** — `npx vitest run lib/accounting.test.ts lib/accounts.test.ts` puis `npm run typecheck`. Expected : vert.

- [ ] **Step 5 : ne pas commiter.**

---

### Task 7 : page « Écritures comptables »

**Files :**
- Create : `frontend/components/ecritures/EcrituresView.tsx`, `AccountingImportWizard.tsx`, `EntriesCard.tsx`, `EntryDetailModal.tsx`
- Modify : `frontend/app/(app)/ecritures/page.tsx`

**Interfaces :**
- Consumes : services et `lib/accounting.ts` (tâche 6) ; `ImportStepper`, `FileDropzone` (`components/releves/ImportSteps.tsx`) ; `fileProblem`, `assignField`, `fieldsByColumn`, `showFirst`, `IMPORTS_AFFICHES`, `formatDateTime` (`lib/statements.ts`) ; `BankLabel`, `logosByCode` ; `DataTable`, `Card`, `Button`, `Modal`, `Field`, `Select`, `TextInput`, `DateInput`, `StatusBadge`, `LoadingState`, `ErrorState`, `EmptyState`, `PageHeader`, `useToast`, `useAuth`, `useCompany`, `formatAmount`, `formatDate`.

Charger le skill `simtis-design` avant cette tâche.

- [ ] **Step 1 : `page.tsx`** — remplacer le `PlaceholderPage` par :

```tsx
import type { Metadata } from "next";

import { EcrituresView } from "@/components/ecritures/EcrituresView";

export const metadata: Metadata = { title: "Écritures comptables" };

export default function Page() {
  return <EcrituresView />;
}
```

- [ ] **Step 2 : `EcrituresView.tsx`** — même ossature que `RelevesView` : `EcrituresView` rend `<Ecritures key={company.id} companyId={company.id} />` ; `Ecritures` charge `listBanks()` (logos), `listAccounts(companyId, { actif: true })` (boutons de compte : ceux qui ont un `journal_sage`) et `listAccountingImports(companyId)` ; `canImport = hasAnyPermission(user.permissions, [PERMISSIONS.ACCOUNTING_IMPORT])` ; `PageHeader` « Écritures comptables », description « Écritures de trésorerie importées de Sage / SI », action bouton `Plus` « Importer un export Sage » (si `canImport` et pas d'import en cours) ; carte « Importer un export Sage » (icône `Upload`) avec `AccountingImportWizard` ; après un import : toast « Export importé : N écritures ajoutées. », encadré de résultat (fichier, écritures par compte avec `BankLabel`, écartées), rechargement de la liste et du journal (`reloadKey`) ; `EntriesCard` ; carte « Journal des imports » (icône `History`) : `DataTable` des 10 derniers (`showFirst(imports, shown, IMPORTS_AFFICHES)`), colonnes « Importé le » (`formatDateTime` + auteur en `text-xs muted`) · Fichier · Période · Écritures ajoutées (droite) · Total débit / crédit (droite, `formatAmount(…, "DH")`), bouton ghost « Afficher N de plus » ; `EmptyState` « Aucun export Sage importé. » avec le bouton d'import.

- [ ] **Step 3 : `AccountingImportWizard.tsx`** — reprendre la structure de `components/releves/ImportWizard.tsx` sans le choix de compte ni l'aperçu modifiable : état `file`, `fileError`, `step` (0 / 1), `analysis`, `mapping`, `feuille`, `ecarter` (bool), `garder` (Set<number>), `busy`, `error` ; `chooseFile` → `fileProblem`, puis `run(file)` = `analyseEntries(file, companyId, { mapping, feuille })` ; `step = analysis.erreurs_mapping.length ? 0 : 1`. Étape 0 : `FileDropzone` + texte « Le fichier est analysé dès qu'il est choisi : seules les lignes banque des journaux de banque (journal Sage de vos comptes) sont retenues. » ; mapping de secours identique à celui des relevés (tableau Colonne fichier · Exemples · Champ SIMTIS avec `Select`, bouton « Valider les colonnes ») ; erreur 409 « Renseignez le journal Sage… » affichée en `Alert` danger avec un lien `Link href="/comptes"` « Aller à l'écran Comptes ». Étape 1 : `Alert` danger si `deja_importe` ; tuiles (`dl` en grille) Lignes à importer (`nb_valides` + doublons gardés) · En erreur · En double · Ignorées · Total débit / crédit · Période ; liste « Par compte » (`BankLabel` + nombre + débit / crédit) ; `DataTable` des lignes : État (`StatusBadge` Valide / Erreur / Doublon, motifs en `text-xs` dessous) · Date · Journal · Compte bancaire (`BankLabel`) · Compte · N° pièce · Libellé · Débit · Crédit · Échéance · Tiers · (pour un doublon interne) case « Garder » ; case « Écarter les lignes en erreur » visible si `nb_erreurs > 0` ; boutons « Changer de fichier » et « Confirmer l'import », désactivé si `deja_importe`, si des erreurs existent sans `ecarter`, ou s'il n'y a aucune ligne à importer. `confirm` → `confirmEntries(file, companyId, { mapping, feuille, garderDoublons: [...garder], ecarterErreurs: ecarter })` puis `onDone(result)`.

- [ ] **Step 4 : `EntriesCard.tsx`** — props `companyId`, `accounts` (avec journal Sage), `logos`, `reloadKey` ; état `filter: EntriesFilter` (page 1), `data`, `state`, `detail: number | null` ; `useEffect` → `listEntries(companyId, filter)` ; changer un filtre remet `page: 1` ; la recherche se lance à la soumission du formulaire (bouton « Rechercher », touche Entrée) pour ne pas appeler l'API à chaque lettre. Rendu : boutons « Tous » + un par compte (mêmes classes que `AccountStatementCard`, sur une ligne qui défile) ; `DateInput` Du / Au ; `Select` Statut (« Tous » + `STATUTS_RAPPROCHEMENT`) ; `TextInput` recherche + bouton ; résumé `dl` Écritures · Total débit · Total crédit ; `DataTable` (Date · Journal · Compte bancaire · N° pièce · Libellé · Débit · Crédit · Échéance · Tiers · Statut) ; chaque ligne a un bouton (icône `Eye`, `aria-label` « Voir l'écriture du JJ/MM/AAAA LIBELLÉ ») qui ouvre `EntryDetailModal` ; pied « Page N sur M » + boutons « Précédent » / « Suivant » désactivés aux extrémités ; `EmptyState` « Aucune écriture sur ces critères. ».

- [ ] **Step 5 : `EntryDetailModal.tsx`** — `Modal` titre « Écriture du JJ/MM/AAAA » ; charge `getEntry(id)` ; `dl` en deux colonnes : Date, Journal, Compte, Compte bancaire, N° pièce, Référence, Libellé, Débit, Crédit, Échéance, Tiers, Statut (badge), Fichier d'origine, Importée le (`formatDateTime`), Par ; bouton « Fermer ». Aucun champ modifiable.

- [ ] **Step 6 : contrôles** — `npx prettier --write components/ecritures app/(app)/ecritures lib types services components/accounts` puis `npm run lint && npm run format:check && npm run typecheck && npm test && npm run build`. Expected : vert.

- [ ] **Step 7 : ne pas commiter.**

---

### Task 8 : contrôle Edge et documentation

**Files :**
- Create (scratchpad, hors dépôt) : `e2e/ecritures.mjs`, `e2e/export_sage_test.xlsx`, `cleanup_ecritures.sql`
- Modify : `CLAUDE.md`, `docs/specs/Plan_Phases_Realisation_SIMTIS.md`, `docs/modele-donnees.md`, `.claude/skills/simtis-design/pages.md`

- [ ] **Step 1 : données de test sur Tefil** — relever d'abord l'état (`SELECT id, journal_sage FROM bank_accounts WHERE company_id = (SELECT id FROM companies WHERE code='SOCX')`) ; via l'API (compte Administrateur de démo ou comptable de démo), donner le journal Sage « TFBQ » au compte BP MAD de Tefil ; générer `export_sage_test.xlsx` (openpyxl, dans le conteneur backend) : 60 lignes banque TFBQ / 5141 (pour la pagination), 3 contreparties, 2 lignes d'un journal ACH, 1 ligne en erreur, 1 doublon interne.

- [ ] **Step 2 : script Edge** (comptable de démo, Tefil) : ouvrir `/ecritures` ; importer le fichier ; Validation : 61 lignes à importer, 1 en erreur, 1 en double, 5 ignorées ; confirmer bloqué ; cocher « Écarter les lignes en erreur » ; confirmer ; liste : 50 lignes, « Page 1 sur 2 », « Suivant » → 11 lignes ; filtre de recherche ; détail d'une écriture ; journal des imports ; Direction : liste visible, pas de bouton d'import ; mobile 390 px : pas de débordement ; aucune erreur JavaScript. Écran Comptes : colonne « Journal Sage » = TFBQ.

- [ ] **Step 3 : nettoyage** — script SQL copié dans le conteneur : supprimer les `accounting_entries` et l'`import_batch` du fichier de test, la ligne `column_mappings` Comptabilité de Tefil si elle a été créée par le test, remettre `journal_sage` du compte BP de Tefil à sa valeur relevée à l'étape 1. Vérifier par un `SELECT`.

- [ ] **Step 4 : documentation**
- `CLAUDE.md` : paragraphe P10 dans « Current state » (routes, règles du journal Sage, lignes banque seulement, aucune correction, pagination par 50, `import_file.py` commun) ; remplacer « Next: … P9 or P10 » par la suite (P11).
- `Plan_Phases_Realisation_SIMTIS.md` : statut « P10 — réalisé le … » sous la phase 10, avec les décisions du 05/10/2026 ; migration 0010.
- `docs/modele-donnees.md` : `bank_accounts.journal_sage` et son index.
- `pages.md` : section `/ecritures` (assistant, liste paginée, détail, journal) et champ « Journal Sage » de l'écran Comptes.

- [ ] **Step 5 : vérification finale** — toutes les commandes de « Global Constraints », résultats lus.

- [ ] **Step 6 : ne pas commiter.**
