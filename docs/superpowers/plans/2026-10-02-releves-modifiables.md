# Relevés modifiables — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** à l'import d'un relevé, afficher l'aperçu au format standard modifiable (corrections sans ajout de ligne) et enregistrer ces corrections tracées ; après l'import, laisser la Trésorerie modifier Pointage, Lettrage / Escompte et Commentaire.

**Architecture:** l'aperçu se modifie dans le navigateur ; la confirmation envoie le fichier et les lignes cochées (champ `lignes`). Le serveur réanalyse le fichier, revérifie chaque ligne envoyée avec **les mêmes règles** (`_read_line` réutilisé), calcule l'origine (`Fichier` / `Corrigée`), garde l'empreinte d'origine et trace les corrections. Une route `PATCH` modifie les trois champs métier après l'import.

**Tech Stack:** FastAPI, SQLAlchemy 2.1, Alembic, PostgreSQL 17, Pydantic 2 ; Next.js 16, React, TypeScript, Tailwind v4, Vitest ; Playwright-core + Edge (contrôle manuel).

**Spec:** `docs/superpowers/specs/2026-10-02-releves-modifiables-design.md`

## Global Constraints

- Langue : français pour l'interface, les messages d'erreur, les commentaires et la documentation.
- Argent : `NUMERIC(18,2)` / `Decimal` côté serveur ; texte exact côté navigateur (`"12500.50"`), **jamais** converti en `number` pour un calcul (sommes en centimes `BigInt`).
- Pas d'ajout de ligne : chaque opération enregistrée vient d'une ligne d'opération du fichier (`numero` obligatoire).
- Après l'import, seuls `pointage_type_id`, `lettrage_escompte`, `commentaire` sont modifiables ; permission `statements.import` (Trésorerie, Administrateur).
- `bank_transactions.origine` ∈ `('Fichier', 'Corrigée')`, défaut `'Fichier'` (migration 0006).
- Couches backend : `api/` mince → `services/` (règles) → `repositories/` (accès base). Erreurs métier : `NotFoundError` (404), `ConflictError` (409) ; schémas d'entrée `extra="forbid"` (422).
- Audit dans la même transaction que la modification (`audit_service.log`), une seule validation (`db.commit()`).
- Sans champ `lignes`, la confirmation garde exactement son comportement actuel (tests existants inchangés).
- UI : tokens `simtis-*`, icônes Lucide, aucun emoji ; skill `simtis-design` à charger avant les tâches frontend.
- Commandes de vérification (toutes doivent passer) : `docker compose run --rm backend ruff check .`, `ruff format --check .`, `pytest`, `alembic check` ; dans `frontend/` : `npm run lint && npm run format:check && npm run typecheck && npm test && npm run build`.
- Commits : l'utilisateur commite lui-même. Les étapes « Commit » de ce plan sont remplacées par « vérifier `git status` » ; ne pas lancer `git commit`.

## Review Focus

- **Montant saisi avec un autre format** (« 1.250,50 », « -150 » dans Débit) : le navigateur doit suivre la règle du serveur (signe ignoré dans Débit / Crédit, valeur absolue) ou signaler la ligne, jamais envoyer un montant que le serveur lirait autrement. → Task 6 (tests `checkDraft`).
- **Pointage devenu inactif entre l'aperçu et la confirmation** : la confirmation doit être refusée avec un message clair, sans rien enregistrer. → Task 3 (test `test_submitted_inactive_pointage_is_refused`).
- **Correction qui rend une ligne identique à une autre ligne du fichier** : les deux doivent s'enregistrer comme deux opérations distinctes (empreintes différentes), pas d'erreur 500. → Task 3 (test `test_corrected_lines_that_become_identical_are_both_saved`).
- **Ligne déjà importée envoyée quand même** (navigateur modifié ou fichier réimporté entre-temps) : 409 « déjà importée », rien d'enregistré. → Task 3 (test `test_submitted_line_already_imported_is_refused`).
- **Correction qui ne change rien** (champ retapé à l'identique, Pointage automatique renvoyé tel quel) : la ligne reste `Fichier`, aucune correction dans l'audit. → Task 3 (test `test_unchanged_submitted_line_stays_from_file`).

---

## File Structure

**Backend**
- Modify `backend/app/models/enums.py` — `ORIGINES_OPERATION`.
- Modify `backend/app/models/imports.py` — colonne `BankTransaction.origine` + CHECK.
- Create `backend/alembic/versions/20261002_1600_0006_origine_operation.py` — colonne + CHECK.
- Modify `backend/tests/test_constraints.py` (contrainte `origine` ; le nombre de tables, 29, ne change pas).
- Modify `backend/app/repositories/import_repository.py` — `get_transaction`, `get_pointage_type`.
- Modify `backend/app/services/import_service.py` — `origine` sur `AnalysedLine`, `confirm_statement(lignes=...)`, `_submitted_lines`, `update_transaction`, `list_pointage_types`.
- Modify `backend/app/schemas/statement.py` — `LigneSoumiseIn`, `LignesSoumisesIn`, `TransactionUpdateIn`, `PointageTypeOut`, `origine` dans `TransactionOut`.
- Modify `backend/app/api/statements.py` — champ `lignes`, `PATCH /statements/transactions/{id}`.
- Modify `backend/app/api/referentiel.py` — `GET /pointage-types`.
- Test `backend/tests/test_statements_api.py`, `backend/tests/test_referentiel_api.py`.

**Frontend**
- Create `frontend/lib/statementLines.ts` (+ `statementLines.test.ts`) — brouillons de lignes, revérification, résumé en centimes.
- Modify `frontend/types/statement.ts` — `LigneSoumise`, `PointageType`, `origine`.
- Modify `frontend/services/statements.ts`, `frontend/services/referentiel.ts`, `frontend/lib/statements.ts` (`importForm` + `lignes`).
- Create `frontend/components/releves/EditablePreview.tsx` — tableau modifiable de l'étape Validation.
- Modify `frontend/components/releves/ImportWizard.tsx` — utilise `EditablePreview`, envoie `lignes`.
- Create `frontend/components/releves/TransactionEditModal.tsx` — modification après l'import.
- Modify `frontend/components/releves/AccountStatementCard.tsx` — icône Modifier, mention « corrigée ».

**Docs** — `CLAUDE.md`, `docs/specs/Plan_Phases_Realisation_SIMTIS.md`, `.claude/skills/simtis-design/pages.md`.

---

### Task 1: colonne `origine` (migration 0006)

**Files:**
- Modify: `backend/app/models/enums.py`
- Modify: `backend/app/models/imports.py` (classe `BankTransaction`)
- Create: `backend/alembic/versions/20261002_1600_0006_origine_operation.py`
- Test: `backend/tests/test_constraints.py`

**Interfaces:**
- Produces: `enums.ORIGINES_OPERATION = ("Fichier", "Corrigée")` ; `BankTransaction.origine: Mapped[str]` (défaut `"Fichier"`).

- [ ] **Step 1: Write the failing tests** (fin de `tests/test_constraints.py`)

```python
# --- Origine d'une opération (migration 0006) ------------------------------------------------------


def test_transaction_origin_defaults_to_file(db, world):
    transaction = save(db, build_transaction(world.statement))
    db.refresh(transaction)

    assert transaction.origine == "Fichier"


def test_transaction_origin_must_be_known(db, world):
    assert_rejected(
        db, "ck_bank_transactions_origine", build_transaction(world.statement, origine="Ajoutée")
    )


def test_corrected_transaction_is_accepted(db, world):
    save(db, build_transaction(world.statement, origine="Corrigée"))
```

- [ ] **Step 2: Run, expect FAIL** — `docker compose run --rm backend pytest tests/test_constraints.py -k origin -q` → `AttributeError`/`TypeError: 'origine' is an invalid keyword argument`.

- [ ] **Step 3: Implement**

`enums.py`, à la fin :

```python
# Origine d'une opération bancaire : telle que le fichier, ou corrigée avant l'enregistrement
ORIGINES_OPERATION = ("Fichier", "Corrigée")
```

`imports.py`, dans `BankTransaction.__table_args__` ajouter `check_in("origine", "origine", enums.ORIGINES_OPERATION),` et la colonne après `statut` :

```python
    # « Corrigée » : au moins un champ modifié dans l'aperçu avant l'enregistrement (tracé dans l'audit)
    origine: Mapped[str] = mapped_column(
        String(10), default="Fichier", server_default="Fichier"
    )
```

Générer puis **relire** la migration : `docker compose run --rm backend alembic revision --autogenerate --rev-id 0006 -m "origine operation"`. Renommer le fichier en `20261002_1600_0006_origine_operation.py` si besoin. Contenu attendu :

```python
def upgrade() -> None:
    op.add_column(
        "bank_transactions",
        sa.Column("origine", sa.String(length=10), server_default="Fichier", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_bank_transactions_origine"),
        "bank_transactions",
        "origine IN ('Fichier', 'Corrigée')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_bank_transactions_origine"), "bank_transactions", type_="check")
    op.drop_column("bank_transactions", "origine")
```

(L'autogénération ne voit pas le CHECK : l'ajouter à la main.)

- [ ] **Step 4: Run, expect PASS** — `pytest tests/test_constraints.py tests/test_migrations.py -q` ; `alembic check` après `docker compose restart backend` → « No new upgrade operations detected ».

- [ ] **Step 5:** `git status` (pas de commit).

---

### Task 2: liste des Pointages (`GET /api/pointage-types`)

**Files:**
- Modify: `backend/app/repositories/import_repository.py`, `backend/app/services/import_service.py`, `backend/app/schemas/statement.py`, `backend/app/api/referentiel.py`
- Test: `backend/tests/test_referentiel_api.py`

**Interfaces:**
- Consumes: `import_repository.active_pointage_types(db) -> list[PointageType]` (existant).
- Produces: `import_service.list_pointage_types(db) -> list[PointageType]` ; `PointageTypeOut {id: int, code: str, libelle: str}` ; route `GET /api/pointage-types` → `list[PointageTypeOut]` triée par libellé.

- [ ] **Step 1: Failing test** (fin de `tests/test_referentiel_api.py`)

```python
def test_pointage_types_are_listed_for_any_logged_in_user(client, reference):
    make_auth_user(reference, "DIRECTION", email="direction.pointage@example.com")
    headers = bearer(login(client, "direction.pointage@example.com"))

    response = client.get("/api/pointage-types", headers=headers)

    assert response.status_code == 200
    assert [item["libelle"] for item in response.json()] == [
        "Décaissement",
        "Encaissement",
        "Frais bancaires",
    ]
    assert set(response.json()[0]) == {"id", "code", "libelle"}


def test_inactive_pointage_types_are_not_listed(client, reference, db):
    frais = db.scalar(select(PointageType).filter_by(code="FRAIS_BANCAIRES"))
    frais.actif = False
    db.flush()
    make_auth_user(reference, "DIRECTION", email="direction.pointage2@example.com")

    body = client.get(
        "/api/pointage-types", headers=bearer(login(client, "direction.pointage2@example.com"))
    ).json()

    assert "FRAIS_BANCAIRES" not in {item["code"] for item in body}


def test_pointage_types_need_a_login(client):
    assert client.get("/api/pointage-types").status_code == 401
```

(Imports à ajouter si absents : `from sqlalchemy import select`, `from app.models import PointageType`, `from tests.helpers import bearer, login, make_auth_user`.)

- [ ] **Step 2: Run, expect FAIL** (404).

- [ ] **Step 3: Implement**

`import_service.py` (section Consultation) :

```python
def list_pointage_types(db: Session) -> list[PointageType]:
    """Types de pointage actifs, par libellé (liste de choix de l'aperçu et de la modification)."""
    return sorted(import_repository.active_pointage_types(db), key=lambda item: item.libelle)
```

(importer `PointageType` depuis `app.models`.)

`schemas/statement.py` :

```python
class PointageTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    libelle: str
```

`api/referentiel.py` :

```python
@router.get("/pointage-types", response_model=list[PointageTypeOut])
def list_pointage_types(db: Session = Depends(get_db)) -> list[PointageTypeOut]:
    """Types d'opération (Pointage) actifs : tout utilisateur connecté."""
    return [PointageTypeOut.model_validate(item) for item in import_service.list_pointage_types(db)]
```

Mettre à jour la docstring du module (« sociétés, devises et types de pointage »).

- [ ] **Step 4: Run, expect PASS** — `pytest tests/test_referentiel_api.py tests/test_permissions.py -q`.

- [ ] **Step 5:** `git status`.

---

### Task 3: confirmation avec les lignes corrigées

**Files:**
- Modify: `backend/app/services/import_service.py`, `backend/app/schemas/statement.py`, `backend/app/api/statements.py`
- Test: `backend/tests/test_statements_api.py`

**Interfaces:**
- Consumes: `_read_line`, `_mark_duplicates`, `_balances`, `Pointages`, `line_hash`, `import_repository.existing_line_hashes`.
- Produces:
  - `AnalysedLine.origine: str = "Fichier"` ;
  - schéma `LigneSoumiseIn` (champs : `numero: int ≥ 1`, `date_operation: str`, `date_valeur: str | None`, `libelle: str | None`, `reference: str | None`, `debit: str | None`, `credit: str | None`, `solde: str | None`, `pointage_type_id: int | None`, `lettrage_escompte: str | None`, `commentaire: str | None`) et `LignesSoumisesIn` (RootModel, liste, numéros uniques) ;
  - `confirm_statement(..., lignes: list[dict] | None = None)` ;
  - champ de formulaire `lignes` (JSON) sur `POST /api/statements/import/confirm`.

- [ ] **Step 1: Failing tests** (nouvelle section en fin de `tests/test_statements_api.py`)

```python
# --- Confirmation avec les lignes corrigées de l'aperçu --------------------------------------------

EDITABLE = [
    HEADER,
    ["24/09/2026", "24/09/2026", "VIR RECU CLIENT ABC", None, 50000, 1050000],
    ["25/09/2026", None, "CHQ FOURNISSEUR", "dix", None, 1037499.5],  # montant illisible
    ["26/09/2026", None, "FRAIS SMS", 10, None, 1037489.5],
]


def submitted(client, headers, account, content):
    """Lignes de l'aperçu, au format attendu par `lignes`, avant toute correction."""
    body = analyse(client, headers, account.id, content).json()
    return [
        {
            "numero": line["numero"],
            "date_operation": line["date_operation"],
            "date_valeur": line["date_valeur"],
            "libelle": line["libelle"],
            "reference": line["reference"],
            "debit": line["debit"],
            "credit": line["credit"],
            "solde": line["solde"],
            "pointage_type_id": line["pointage_type_id"],
            "lettrage_escompte": line["lettrage_escompte"],
            "commentaire": line["commentaire"],
        }
        for line in body["lignes"]
    ]


def test_corrected_lines_are_saved_with_their_origin(client, tresorerie, account, db):
    content = xlsx(("Relevé", EDITABLE))
    lines = submitted(client, tresorerie, account, content)
    lines[1] |= {"debit": "12500.50", "credit": "0.00"}  # ligne en erreur corrigée
    lines[2]["commentaire"] = "Frais du mois"  # ligne valide corrigée

    response = confirm(client, tresorerie, account.id, content, lignes=lines)

    assert response.status_code == 201, response.text
    rows = transactions(db, account)
    assert [(row.libelle, row.debit, row.origine) for row in rows] == [
        ("VIR RECU CLIENT ABC", Decimal("0.00"), "Fichier"),
        ("CHQ FOURNISSEUR", Decimal("12500.50"), "Corrigée"),
        ("FRAIS SMS", Decimal("10.00"), "Corrigée"),
    ]
    assert rows[2].commentaire == "Frais du mois"
    [entry] = db.scalars(select(AuditLog).filter_by(action="import_releve")).all()
    corrections = entry.nouvelle_valeur["lignes_corrigees"]
    assert {"numero": 4, "champ": "commentaire", "avant": None, "apres": "Frais du mois"} in corrections
    assert {"numero": 3, "champ": "debit", "avant": None, "apres": "12500.50"} in corrections


def test_unchecked_file_line_is_not_saved_and_is_audited(client, tresorerie, account, db):
    content = xlsx(("Relevé", EDITABLE))
    lines = submitted(client, tresorerie, account, content)

    confirm(client, tresorerie, account.id, content, lignes=[lines[0], lines[2]])

    assert [row.libelle for row in transactions(db, account)] == ["VIR RECU CLIENT ABC", "FRAIS SMS"]
    [entry] = db.scalars(select(AuditLog).filter_by(action="import_releve")).all()
    assert entry.nouvelle_valeur["lignes_fichier_non_importees"] == [3]


def test_unchanged_submitted_line_stays_from_file(client, tresorerie, account, db):
    content = xlsx(("Relevé", EDITABLE))
    lines = submitted(client, tresorerie, account, content)

    confirm(client, tresorerie, account.id, content, lignes=[lines[0]])

    assert [row.origine for row in transactions(db, account)] == ["Fichier"]
    [entry] = db.scalars(select(AuditLog).filter_by(action="import_releve")).all()
    assert entry.nouvelle_valeur["lignes_corrigees"] == []


def test_corrected_line_keeps_its_original_fingerprint(client, tresorerie, account, db):
    content = xlsx(("Relevé", EDITABLE))
    lines = submitted(client, tresorerie, account, content)
    lines[0]["libelle"] = "VIR RECU CLIENT ABC CORRIGE"
    confirm(client, tresorerie, account.id, content, lignes=[lines[0]])
    # La banque renvoie plus tard la même opération, dans sa version d'origine
    again = xlsx(("Relevé", [HEADER, EDITABLE[1]]))

    preview = analyse(client, tresorerie, account.id, again).json()

    assert preview["lignes"][0]["statut"] == "Doublon"
    assert preview["lignes"][0]["motifs"] == ["Déjà importée pour ce compte."]


def test_corrected_lines_that_become_identical_are_both_saved(client, tresorerie, account, db):
    rows = [HEADER, ["24/09/2026", None, "A", "dix", None, None], ["24/09/2026", None, "A", "onze", None, None]]
    content = xlsx(("Relevé", rows))
    lines = submitted(client, tresorerie, account, content)
    for line in lines:
        line |= {"debit": "10.00", "credit": "0.00"}

    response = confirm(client, tresorerie, account.id, content, lignes=lines)

    assert response.status_code == 201, response.text
    assert len({row.hash_ligne for row in transactions(db, account)}) == 2


def test_invalid_submitted_line_refuses_everything(client, tresorerie, account, db):
    content = xlsx(("Relevé", EDITABLE))
    lines = submitted(client, tresorerie, account, content)  # ligne 3 toujours illisible
    before = counts(db)

    response = confirm(client, tresorerie, account.id, content, lignes=lines)

    assert response.status_code == 409
    assert response.json()["detail"].startswith("Ligne 3 : Ni débit ni crédit.")
    assert counts(db) == before


@pytest.mark.parametrize(
    ("change", "detail"),
    [
        ({"numero": 99}, "La ligne 99 n'est pas une opération du fichier."),
        ({"numero": 1}, "La ligne 1 n'est pas une opération du fichier."),
    ],
)
def test_submitted_line_must_come_from_the_file(client, tresorerie, account, change, detail):
    content = xlsx(("Relevé", EDITABLE))
    lines = submitted(client, tresorerie, account, content)

    response = confirm(client, tresorerie, account.id, content, lignes=[lines[0] | change])

    assert response.status_code == 409
    assert response.json() == {"detail": detail}


def test_submitted_line_already_imported_is_refused(client, tresorerie, account, db):
    content = xlsx(("Relevé", EDITABLE))
    lines = submitted(client, tresorerie, account, content)
    confirm(client, tresorerie, account.id, xlsx(("Relevé", [HEADER, EDITABLE[1]])), nom="autre.xlsx")

    response = confirm(client, tresorerie, account.id, content, lignes=[lines[0]])

    assert response.status_code == 409
    assert response.json() == {"detail": "Ligne 2 : déjà importée pour ce compte."}


def test_submitted_inactive_pointage_is_refused(client, tresorerie, account, db):
    content = xlsx(("Relevé", EDITABLE))
    lines = submitted(client, tresorerie, account, content)
    frais = db.scalar(select(PointageType).filter_by(code="FRAIS_BANCAIRES"))
    frais.actif = False
    db.flush()

    response = confirm(
        client, tresorerie, account.id, content, lignes=[lines[0] | {"pointage_type_id": frais.id}]
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Ligne 2 : Pointage inconnu ou inactif."}


@pytest.mark.parametrize(
    "extra",
    [{"garder_doublons": [3]}, {"ecarter_erreurs": True}],
)
def test_lines_cannot_be_combined_with_the_old_options(client, tresorerie, account, extra):
    content = xlsx(("Relevé", EDITABLE))
    lines = submitted(client, tresorerie, account, content)

    response = confirm(client, tresorerie, account.id, content, lignes=lines[:1], **extra)

    assert response.status_code == 422


@pytest.mark.parametrize("value", ["[]", "pas du json", '[{"numero": 2}, {"numero": 2}]'])
def test_malformed_lines_give_422_or_409(client, tresorerie, account, value):
    content = xlsx(("Relevé", EDITABLE))
    data = {"bank_account_id": str(account.id), "lignes": value}
    files = {"fichier": ("releve.xlsx", content, "application/octet-stream")}

    response = client.post(CONFIRM_URL, data=data, files=files, headers=tresorerie)

    assert response.status_code == (409 if value == "[]" else 422)
```

Ajouter `PointageType` aux imports si absent ; dans le helper `confirm`, un `list[dict]` est déjà sérialisé en JSON.

- [ ] **Step 2: Run, expect FAIL** — `pytest tests/test_statements_api.py -k "submitted or corrected or unchecked or lines_cannot or malformed_lines" -q`.

- [ ] **Step 3: Implement**

**Schéma** (`schemas/statement.py`) :

```python
class LigneSoumiseIn(BaseModel):
    """Une ligne du fichier, telle que l'utilisateur l'a laissée dans l'aperçu (corrigée ou non).

    Les valeurs sont revérifiées par le serveur avec les mêmes règles que l'analyse : on les reçoit
    en texte, comme des cellules de fichier.
    """

    model_config = ConfigDict(extra="forbid")

    numero: Annotated[int, Field(ge=1)]
    date_operation: str | None = None
    date_valeur: str | None = None
    libelle: str | None = Field(default=None, max_length=500)
    reference: str | None = Field(default=None, max_length=60)
    debit: str | None = None
    credit: str | None = None
    solde: str | None = None
    pointage_type_id: int | None = None
    lettrage_escompte: str | None = Field(default=None, max_length=200)
    commentaire: str | None = Field(default=None, max_length=1000)


class LignesSoumisesIn(RootModel[list[LigneSoumiseIn]]):
    """Lignes à importer ; un même numéro ne peut pas apparaître deux fois."""

    @model_validator(mode="after")
    def _numeros_uniques(self) -> "LignesSoumisesIn":
        numeros = [line.numero for line in self.root]
        if len(numeros) != len(set(numeros)):
            raise ValueError("Une ligne du fichier apparaît deux fois.")
        return self
```

(importer `model_validator`.)

**Service** (`import_service.py`) :

1. `AnalysedLine` : ajouter `origine: str = "Fichier"` (avant `hash_ligne`).
2. Constantes et helper :

```python
# Champs comparés pour décider qu'une ligne a été corrigée (et tracés dans l'audit)
CORRECTABLE_FIELDS = (
    "date_operation",
    "date_valeur",
    "libelle",
    "reference",
    "debit",
    "credit",
    "solde",
    "pointage_type_id",
    "lettrage_escompte",
    "commentaire",
)
# Une ligne reçue se lit comme une ligne de fichier aux colonnes Débit / Crédit séparées
_SUBMITTED_MAPPING: Mapping = {"debit": 0, "credit": 1}


def _submitted_line(
    data: dict, original: AnalysedLine, bank: Bank, today: date, pointages: Pointages
) -> AnalysedLine:
    """Revérifie une ligne envoyée avec les règles de l'analyse (`_read_line`)."""
    cells = {
        code: data.get(code)
        for code in (
            "date_operation",
            "date_valeur",
            "libelle",
            "reference",
            "debit",
            "credit",
            "solde",
            "lettrage_escompte",
            "commentaire",
        )
    }
    line = _read_line(original.numero, cells, _SUBMITTED_MAPPING, bank, today, pointages)
    chosen = data.get("pointage_type_id")
    if chosen is not None:
        if chosen not in pointages.labels:
            line.motifs.append("Pointage inconnu ou inactif.")
            line.statut = "Erreur"
        else:
            line.pointage_type_id, line.pointage_auto = chosen, False
            line.pointage_libelle = pointages.labels[chosen]
    return line


def _corrections(original: AnalysedLine, line: AnalysedLine) -> list[dict]:
    return [
        {"numero": line.numero, "champ": name, "avant": getattr(original, name), "apres": getattr(line, name)}
        for name in CORRECTABLE_FIELDS
        if getattr(original, name) != getattr(line, name)
    ]
```

3. Sélection des lignes envoyées (appelée par `confirm_statement`) :

```python
@dataclass
class Selection:
    lines: list[AnalysedLine]
    corrections: list[dict]
    not_imported: list[int]
    nb_erreurs: int
    nb_doublons: int


def _submitted_selection(
    db: Session, analysis: StatementAnalysis, lignes: list[dict], today: date
) -> Selection:
    """Lignes envoyées par l'aperçu : revérifiées, origine et empreinte fixées. Rien n'est écrit."""
    if not lignes:
        raise ConflictError("Aucune ligne à importer dans ce fichier.")
    account = analysis.account
    pointages = _pointages(db)
    originals = {line.numero: line for line in analysis.lignes}
    lines, corrections, problems = [], [], []
    for data in lignes:
        original = originals.get(data["numero"])
        if original is None:
            raise ConflictError(f"La ligne {data['numero']} n'est pas une opération du fichier.")
        if original.statut == "Doublon" and original.doublon_de is None:
            problems.append(f"Ligne {original.numero} : déjà importée pour ce compte.")
            continue
        line = _submitted_line(data, original, account.bank, today, pointages)
        if line.motifs:
            problems.append(f"Ligne {line.numero} : {' '.join(line.motifs)}")
            continue
        changes = _corrections(original, line)
        line.origine = "Corrigée" if changes else "Fichier"
        corrections.extend(changes)
        # Empreinte d'origine : la même opération renvoyée par la banque sera reconnue
        line.hash_ligne = original.hash_ligne
        lines.append(line)
    if problems:
        raise ConflictError(" ".join(problems))

    # Ligne d'origine en erreur : empreinte calculée sur ses valeurs corrigées
    occurrences: Counter[tuple] = Counter()
    for line in lines:
        if line.hash_ligne is None:
            key = (line.date_operation, line.date_valeur, line.libelle, line.debit, line.credit, line.solde, line.reference)
            occurrences[key] += 1
            line.hash_ligne = line_hash(account.id, (*key, "corrigée"), occurrences[key])
    known = import_repository.existing_line_hashes(db, account.id, [line.hash_ligne for line in lines])
    already = [f"Ligne {line.numero} : déjà importée pour ce compte." for line in lines if line.hash_ligne in known]
    if already:
        raise ConflictError(" ".join(already))

    kept = {line.numero for line in lines}
    return Selection(
        lines=sorted(lines, key=lambda line: line.numero),
        corrections=corrections,
        not_imported=sorted(numero for numero in originals if numero not in kept),
        nb_erreurs=sum(1 for line in analysis.lignes if line.statut == "Erreur" and line.numero not in kept),
        nb_doublons=sum(1 for line in analysis.lignes if line.statut == "Doublon" and line.numero not in kept),
    )
```

Note sur l'empreinte « corrigée » : on ajoute le marqueur `"corrigée"` à la clé pour qu'une ligne corrigée ne prenne jamais l'empreinte d'une ligne valide du fichier (test `test_corrected_lines_that_become_identical_are_both_saved`).

4. `confirm_statement` : ajouter le paramètre `lignes: list[dict] | None = None`. Après les contrôles `erreurs_mapping` / `deja_importe` :

```python
    if lignes is not None:
        selection = _submitted_selection(db, analysis, lignes, today or position_service.business_today())
    else:
        selection = _file_selection(analysis, garder_doublons, ecarter_erreurs)
    lines = selection.lines
```

`_file_selection` reprend **sans changement** le code actuel (erreurs bloquantes sauf `ecarter_erreurs`, `garder_doublons`, « Aucune ligne à importer ») et renvoie `Selection(lines, [], [numéros non retenus], len(errors), skipped_duplicates)`. Remplacer ensuite `len(errors)` par `selection.nb_erreurs` et `skipped_duplicates` par `selection.nb_doublons` dans `ImportBatch`, la réponse et l'audit. Enregistrer `origine=line.origine` dans `BankTransaction(...)`. Ajouter à l'audit `"lignes_corrigees": selection.corrections` et `"lignes_fichier_non_importees": selection.not_imported`.

**API** (`api/statements.py`) — paramètre de formulaire et contrôle :

```python
    lignes: Annotated[
        str | None,
        Form(description="JSON : lignes du fichier à importer, avec leurs corrections (aperçu)"),
    ] = None,
```

```python
    submitted = _json_field(LignesSoumisesIn, "lignes", lignes)
    if submitted is not None and (garder_doublons or ecarter_erreurs):
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("body", "lignes"),
                    "msg": "« lignes » remplace « garder_doublons » et « ecarter_erreurs ».",
                    "input": None,
                }
            ]
        )
    ...
        lignes=None if submitted is None else [line.model_dump() for line in submitted.root],
```

Une liste vide `[]` est valide pour le schéma : le service répond 409 « Aucune ligne à importer dans ce fichier. ».

- [ ] **Step 4: Run, expect PASS** — `pytest tests/test_statements_api.py -q` (anciens tests compris).

- [ ] **Step 5:** `git status`.

---

### Task 4: `origine` dans les réponses et modification après l'import

**Files:**
- Modify: `backend/app/repositories/import_repository.py`, `backend/app/services/import_service.py`, `backend/app/schemas/statement.py`, `backend/app/api/statements.py`
- Test: `backend/tests/test_statements_api.py`

**Interfaces:**
- Produces:
  - `TransactionOut.origine: str` (après `statut`) ;
  - `TransactionUpdateIn {pointage_type_id: int | None, lettrage_escompte: str | None (≤ 120), commentaire: str | None (≤ 1000)}`, `extra="forbid"` ;
  - `import_service.update_transaction(db, transaction_id, *, pointage_type_id, lettrage_escompte, commentaire, acteur_id, ip) -> tuple[BankTransaction, str | None]` (opération, libellé du pointage) ;
  - route `PATCH /api/statements/transactions/{transaction_id}` → `TransactionOut`, permission `statements.import`.

- [ ] **Step 1: Failing tests**

```python
# --- Modification après l'import (champs métier) ---------------------------------------------------


def first_transaction(client, tresorerie, account, db) -> BankTransaction:
    confirm(client, tresorerie, account.id, xlsx(("Relevé", STATEMENT)))
    return transactions(db, account)[0]


def patch(client, headers, transaction_id, body):
    return client.patch(f"/api/statements/transactions/{transaction_id}", json=body, headers=headers)


def test_business_fields_can_be_changed_and_are_audited(client, tresorerie, account, db):
    transaction = first_transaction(client, tresorerie, account, db)
    frais = pointage_id(db, "FRAIS_BANCAIRES")

    response = patch(
        client,
        tresorerie,
        transaction.id,
        {"pointage_type_id": frais, "lettrage_escompte": " L-12 ", "commentaire": "Vu avec la banque"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["pointage"], body["lettrage_escompte"], body["commentaire"], body["origine"]) == (
        "Frais bancaires",
        "L-12",
        "Vu avec la banque",
        "Fichier",
    )
    [entry] = db.scalars(select(AuditLog).filter_by(action="modification_operation")).all()
    assert entry.ancienne_valeur == {
        "pointage_type_id": pointage_id(db, "ENCAISSEMENT"),
        "lettrage_escompte": None,
        "commentaire": None,
    }
    assert entry.nouvelle_valeur["commentaire"] == "Vu avec la banque"


def test_same_values_write_no_audit(client, tresorerie, account, db):
    transaction = first_transaction(client, tresorerie, account, db)
    body = {"pointage_type_id": transaction.pointage_type_id, "lettrage_escompte": None, "commentaire": "  "}

    patch(client, tresorerie, transaction.id, body)

    assert db.scalars(select(AuditLog).filter_by(action="modification_operation")).all() == []


@pytest.mark.parametrize("field", ["debit", "libelle", "date_operation", "solde"])
def test_bank_fields_cannot_be_changed(client, tresorerie, account, db, field):
    transaction = first_transaction(client, tresorerie, account, db)

    response = patch(client, tresorerie, transaction.id, {"commentaire": None, field: "1"})

    assert response.status_code == 422


def test_inactive_pointage_is_refused(client, tresorerie, account, db):
    transaction = first_transaction(client, tresorerie, account, db)
    frais = db.scalar(select(PointageType).filter_by(code="FRAIS_BANCAIRES"))
    frais.actif = False
    db.flush()

    response = patch(client, tresorerie, transaction.id, {"pointage_type_id": frais.id})

    assert response.status_code == 409
    assert response.json() == {"detail": "Pointage inconnu ou inactif."}


def test_unknown_transaction_gives_404(client, tresorerie):
    assert patch(client, tresorerie, 999999, {"commentaire": "x"}).status_code == 404


@pytest.mark.parametrize("role", ["COMPTABLE", "DIRECTION"])
def test_only_importers_can_change_a_transaction(client, reference, tresorerie, account, db, role):
    transaction = first_transaction(client, tresorerie, account, db)
    make_auth_user(reference, role, email=f"{role.lower()}.patch@example.com")
    headers = bearer(login(client, f"{role.lower()}.patch@example.com"))

    assert patch(client, headers, transaction.id, {"commentaire": "x"}).status_code == 403
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement**

`import_repository.py` :

```python
def get_transaction(db: Session, transaction_id: int) -> BankTransaction | None:
    return db.get(BankTransaction, transaction_id)


def get_pointage_type(db: Session, pointage_type_id: int) -> PointageType | None:
    return db.get(PointageType, pointage_type_id)
```

`import_service.py` :

```python
BUSINESS_FIELDS = ("pointage_type_id", "lettrage_escompte", "commentaire")


def update_transaction(
    db: Session,
    transaction_id: int,
    *,
    pointage_type_id: int | None,
    lettrage_escompte: str | None,
    commentaire: str | None,
    acteur_id: int,
    ip: str | None = None,
) -> tuple[BankTransaction, str | None]:
    """Modifie les champs métier d'une opération importée (décision métier du 02/10/2026).

    Dates, libellé et montants restent ceux de la banque. Seuls les champs changés sont tracés.
    """
    transaction = import_repository.get_transaction(db, transaction_id)
    if transaction is None:
        raise NotFoundError("Opération introuvable.")
    pointage = None
    if pointage_type_id is not None:
        pointage = import_repository.get_pointage_type(db, pointage_type_id)
        if pointage is None or not pointage.actif:
            raise ConflictError("Pointage inconnu ou inactif.")
    new_values = {
        "pointage_type_id": pointage_type_id,
        "lettrage_escompte": clean_text(lettrage_escompte),
        "commentaire": clean_text(commentaire),
    }
    changed = [name for name in BUSINESS_FIELDS if getattr(transaction, name) != new_values[name]]
    if changed:
        avant = {name: getattr(transaction, name) for name in changed}
        for name in changed:
            setattr(transaction, name, new_values[name])
        audit_service.log(
            db,
            user_id=acteur_id,
            action="modification_operation",
            entite="bank_transaction",
            entite_id=transaction.id,
            avant=avant,
            apres={name: new_values[name] for name in changed},
            ip=ip,
        )
        db.commit()
    label = pointage.libelle if pointage else None
    return transaction, label
```

(`clean_text` réduit les espaces et rend `None` pour un texte vide : « L-12 » ; le libellé du pointage est relu par `TransactionOut`.)

`schemas/statement.py` : ajouter `origine: str` à `TransactionOut` (après `statut`, `origine=transaction.origine` dans `from_row`), et :

```python
class TransactionUpdateIn(BaseModel):
    """Champs métier d'une opération importée : les seuls modifiables après l'import."""

    model_config = ConfigDict(extra="forbid")

    pointage_type_id: int | None = None
    lettrage_escompte: str | None = Field(default=None, max_length=120)
    commentaire: str | None = Field(default=None, max_length=1000)
```

`api/statements.py` :

```python
@router.patch("/transactions/{transaction_id}", response_model=TransactionOut)
def update_transaction(
    transaction_id: int,
    body: TransactionUpdateIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_import),
) -> TransactionOut:
    """Modifie Pointage, Lettrage / Escompte et Commentaire d'une opération importée."""
    transaction, pointage = import_service.update_transaction(
        db, transaction_id, **body.model_dump(), acteur_id=user.id, ip=client_ip(request)
    )
    return TransactionOut.from_row(transaction.statement.bank_account, transaction, pointage)
```

Placer cette route **avant** `@router.get("/{statement_id}/transactions")` n'est pas nécessaire (méthodes différentes), mais garder les routes « transactions » regroupées.

- [ ] **Step 4: Run, expect PASS** — `pytest tests/test_statements_api.py -q`, puis la suite complète, `ruff check .`, `ruff format --check .`, `alembic check`.

- [ ] **Step 5:** `git status`.

---

### Task 5: client API et types (frontend)

**Files:**
- Modify: `frontend/types/statement.ts`, `frontend/lib/statements.ts`, `frontend/lib/statements.test.ts`, `frontend/services/statements.ts`, `frontend/services/referentiel.ts`

**Interfaces:**
- Produces:
  - `type LigneSoumise = { numero: number; date_operation: string | null; date_valeur: string | null; libelle: string | null; reference: string | null; debit: string | null; credit: string | null; solde: string | null; pointage_type_id: number | null; lettrage_escompte: string | null; commentaire: string | null }` ;
  - `type PointageType = { id: number; code: string; libelle: string }` ;
  - `Transaction.origine: "Fichier" | "Corrigée"` ;
  - `ConfirmOptions` devient `{ garderDoublons: number[]; ecarterErreurs: boolean } | { lignes: LigneSoumise[] }` ;
  - `importForm(request, options)` ajoute `lignes` (JSON) quand elles sont données, sans `garder_doublons` ni `ecarter_erreurs` ;
  - `listPointageTypes(): Promise<PointageType[]>` (`services/referentiel.ts`) ;
  - `updateTransaction(id, data: { pointage_type_id: number | null; lettrage_escompte: string | null; commentaire: string | null }): Promise<Transaction>` (`services/statements.ts`, `PATCH`, JSON).

- [ ] **Step 1: Failing test** (`lib/statements.test.ts`, bloc `importForm`)

```ts
  it("envoie les lignes de l'aperçu à la place des anciennes options", () => {
    const ligne = {
      numero: 2,
      date_operation: "2026-09-24",
      date_valeur: null,
      libelle: "VIR",
      reference: null,
      debit: null,
      credit: "10.00",
      solde: null,
      pointage_type_id: 1,
      lettrage_escompte: null,
      commentaire: null,
    };

    const form = importForm({ file, accountId: 7 }, { lignes: [ligne] });

    expect(JSON.parse(form.get("lignes") as string)).toEqual([ligne]);
    expect(form.has("garder_doublons")).toBe(false);
    expect(form.has("ecarter_erreurs")).toBe(false);
  });
```

- [ ] **Step 2: Run, expect FAIL** — `npx vitest run lib/statements.test.ts`.

- [ ] **Step 3: Implement** — dans `importForm` :

```ts
  if (options && "lignes" in options) {
    form.append("lignes", JSON.stringify(options.lignes));
  } else if (options) {
    // ancien fonctionnement : garder_doublons / ecarter_erreurs (code actuel inchangé)
  }
```

Ajouter les types ci-dessus, `listPointageTypes` (`apiFetch<PointageType[]>("/pointage-types")`) et `updateTransaction` (`apiFetch<Transaction>(\`/statements/transactions/${id}\`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) })`).

- [ ] **Step 4: Run, expect PASS** — `npx vitest run lib/statements.test.ts && npm run typecheck`.

- [ ] **Step 5:** `git status`.

---

### Task 6: brouillons de lignes, revérification et résumé (`lib/statementLines.ts`)

**Files:**
- Create: `frontend/lib/statementLines.ts`, `frontend/lib/statementLines.test.ts`

**Interfaces:**
- Consumes: `normalizeAmountInput` (`lib/accounts`), `normalizeSignedAmountInput` (`lib/balances`), types `AnalysedLine`, `LigneSoumise`.
- Produces:
  - `type LineDraft = { numero: number; date_operation: string; date_valeur: string; libelle: string; reference: string; debit: string; credit: string; solde: string; pointage_type_id: number | null; lettrage_escompte: string; commentaire: string }` (textes tels que saisis, `""` = vide) ;
  - `draftFromLine(line: AnalysedLine): LineDraft` ;
  - `amountToInput(value: string | null): string` (`"12500.50"` → `"12 500,50"`, sans `number`) ;
  - `checkDraft(draft: LineDraft, today: string): string[]` (motifs, mêmes règles que le serveur) ;
  - `draftToLigne(draft: LineDraft): LigneSoumise` ;
  - `sameDraft(a: LineDraft, b: LineDraft): boolean` ;
  - `summariseDrafts(drafts: LineDraft[], fileOpening: string | null, fileClosing: string | null): DraftSummary` avec `DraftSummary = { count: number; totalDebit: string; totalCredit: string; periodeDebut: string | null; periodeFin: string | null; ouverture: string | null; cloture: string | null; coherent: boolean | null }` (montants en texte exact `"12500.50"`).

- [ ] **Step 1: Failing tests** (`lib/statementLines.test.ts`)

```ts
import { describe, expect, it } from "vitest";

import {
  amountToInput,
  checkDraft,
  draftToLigne,
  sameDraft,
  summariseDrafts,
  type LineDraft,
} from "./statementLines";

const TODAY = "2026-10-02";
const base: LineDraft = {
  numero: 2,
  date_operation: "2026-09-24",
  date_valeur: "",
  libelle: "VIR CLIENT",
  reference: "",
  debit: "",
  credit: "45 000",
  solde: "165 000",
  pointage_type_id: null,
  lettrage_escompte: "",
  commentaire: "",
};

describe("amountToInput", () => {
  it("écrit le montant à la française sans calcul flottant", () => {
    expect(amountToInput("12500.50")).toBe("12 500,50");
    expect(amountToInput("-1037349.50")).toBe("-1 037 349,50");
    expect(amountToInput("10.00")).toBe("10");
    expect(amountToInput(null)).toBe("");
  });
});

describe("checkDraft", () => {
  it("accepte une ligne complète", () => {
    expect(checkDraft(base, TODAY)).toEqual([]);
  });

  it("applique les règles du serveur", () => {
    expect(checkDraft({ ...base, date_operation: "" }, TODAY)).toContain("Date d'opération manquante.");
    expect(checkDraft({ ...base, date_operation: "2026-10-03" }, TODAY)).toContain(
      "Date d'opération dans le futur.",
    );
    expect(checkDraft({ ...base, libelle: "  " }, TODAY)).toContain("Libellé manquant.");
    expect(checkDraft({ ...base, credit: "" }, TODAY)).toContain("Ni débit ni crédit.");
    expect(checkDraft({ ...base, debit: "5" }, TODAY)).toContain(
      "Débit et crédit renseignés sur la même ligne.",
    );
    expect(checkDraft({ ...base, credit: "dix" }, TODAY)).toContain(
      "Crédit : montant illisible (ex. 12 500,50).",
    );
    expect(checkDraft({ ...base, lettrage_escompte: "x".repeat(121) }, TODAY)).toContain(
      "Lettrage / Escompte : 120 caractères au plus.",
    );
  });

  it("lit un débit négatif comme un débit, comme le serveur", () => {
    expect(checkDraft({ ...base, credit: "", debit: "-150" }, TODAY)).toEqual([]);
    expect(draftToLigne({ ...base, credit: "", debit: "-150" }).debit).toBe("150");
  });

  it("signale un format que le navigateur ne sait pas lire, au lieu de l'envoyer", () => {
    // « 1.250,50 » (point des milliers) : signalé, jamais envoyé sous une autre valeur
    expect(checkDraft({ ...base, credit: "1.250,50" }, TODAY)).toContain(
      "Crédit : montant illisible (ex. 12 500,50).",
    );
  });
});

describe("draftToLigne", () => {
  it("normalise les montants et vide les textes blancs", () => {
    expect(draftToLigne(base)).toEqual({
      numero: 2,
      date_operation: "2026-09-24",
      date_valeur: null,
      libelle: "VIR CLIENT",
      reference: null,
      debit: null,
      credit: "45000",
      solde: "165000",
      pointage_type_id: null,
      lettrage_escompte: null,
      commentaire: null,
    });
  });
});

describe("sameDraft", () => {
  it("compare toutes les valeurs", () => {
    expect(sameDraft(base, { ...base })).toBe(true);
    expect(sameDraft(base, { ...base, commentaire: "x" })).toBe(false);
  });
});

describe("summariseDrafts", () => {
  const lines: LineDraft[] = [
    base,
    { ...base, numero: 3, date_operation: "2026-09-25", credit: "", debit: "250,50", solde: "164 749,50" },
  ];

  it("totalise en centimes exacts et vérifie la cohérence avec le solde initial du fichier", () => {
    expect(summariseDrafts(lines, "120000.00", null)).toEqual({
      count: 2,
      totalDebit: "250.50",
      totalCredit: "45000.00",
      periodeDebut: "2026-09-24",
      periodeFin: "2026-09-25",
      ouverture: "120000.00",
      cloture: "164749.50",
      coherent: true,
    });
  });

  it("déduit l'ouverture de la première ligne sans solde initial", () => {
    expect(summariseDrafts(lines, null, null).ouverture).toBe("120000.00");
  });

  it("ne conclut rien sans soldes", () => {
    const sansSolde = lines.map((line) => ({ ...line, solde: "" }));
    expect(summariseDrafts(sansSolde, null, null).coherent).toBeNull();
  });
});
```

- [ ] **Step 2: Run, expect FAIL** — `npx vitest run lib/statementLines.test.ts`.

- [ ] **Step 3: Implement** (`lib/statementLines.ts`)

```ts
/**
 * Aperçu modifiable d'un relevé : brouillons de lignes, revérification (mêmes règles que
 * `backend/app/services/import_service._read_line`) et résumé. Les montants restent du TEXTE ;
 * les sommes se font en centimes `BigInt`, jamais en nombre à virgule flottante.
 */
import { normalizeAmountInput } from "@/lib/accounts";
import { normalizeSignedAmountInput } from "@/lib/balances";
import type { AnalysedLine, LigneSoumise } from "@/types/statement";

export type LineDraft = {
  numero: number;
  date_operation: string;
  date_valeur: string;
  libelle: string;
  reference: string;
  debit: string;
  credit: string;
  solde: string;
  pointage_type_id: number | null;
  lettrage_escompte: string;
  commentaire: string;
};

export type DraftSummary = {
  count: number;
  totalDebit: string;
  totalCredit: string;
  periodeDebut: string | null;
  periodeFin: string | null;
  ouverture: string | null;
  cloture: string | null;
  coherent: boolean | null;
};

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/** « 12500.50 » → « 12 500,50 » ; décimales nulles retirées ; uniquement des chaînes. */
export function amountToInput(value: string | null): string {
  if (value === null) return "";
  const negative = value.startsWith("-");
  const [whole, decimals = ""] = (negative ? value.slice(1) : value).split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  const cents = decimals.replace(/0+$/, "");
  return `${negative ? "-" : ""}${grouped}${cents ? `,${decimals.padEnd(2, "0")}` : ""}`;
}

export function draftFromLine(line: AnalysedLine): LineDraft {
  return {
    numero: line.numero,
    date_operation: line.date_operation ?? "",
    date_valeur: line.date_valeur ?? "",
    libelle: line.libelle ?? "",
    reference: line.reference ?? "",
    debit: line.debit && line.debit !== "0.00" ? amountToInput(line.debit) : "",
    credit: line.credit && line.credit !== "0.00" ? amountToInput(line.credit) : "",
    solde: amountToInput(line.solde),
    pointage_type_id: line.pointage_type_id,
    lettrage_escompte: line.lettrage_escompte ?? "",
    commentaire: line.commentaire ?? "",
  };
}

/** Montant de Débit / Crédit : signe ignoré (valeur absolue), comme le serveur. */
function unsigned(text: string): string | null {
  const trimmed = text.trim().replace(/^[-−+]/, "");
  return normalizeAmountInput(trimmed);
}

export function checkDraft(draft: LineDraft, today: string): string[] {
  const motifs: string[] = [];
  if (!draft.date_operation) motifs.push("Date d'opération manquante.");
  else if (!ISO_DATE.test(draft.date_operation)) motifs.push("Date d'opération illisible.");
  else if (draft.date_operation > today) motifs.push("Date d'opération dans le futur.");
  if (draft.date_valeur && !ISO_DATE.test(draft.date_valeur)) {
    motifs.push("Date de valeur illisible.");
  }
  if (!draft.libelle.trim()) motifs.push("Libellé manquant.");
  const debitText = draft.debit.trim();
  const creditText = draft.credit.trim();
  const debit = debitText ? unsigned(debitText) : null;
  const credit = creditText ? unsigned(creditText) : null;
  if (debitText && debit === null) motifs.push("Débit : montant illisible (ex. 12 500,50).");
  if (creditText && credit === null) motifs.push("Crédit : montant illisible (ex. 12 500,50).");
  const hasDebit = debit !== null && toCents(debit) !== 0n;
  const hasCredit = credit !== null && toCents(credit) !== 0n;
  if ((!debitText || debit !== null) && (!creditText || credit !== null)) {
    if (hasDebit && hasCredit) motifs.push("Débit et crédit renseignés sur la même ligne.");
    else if (!hasDebit && !hasCredit) motifs.push("Ni débit ni crédit.");
  }
  if (draft.solde.trim() && normalizeSignedAmountInput(draft.solde) === null) {
    motifs.push("Solde : montant illisible (ex. -15 000,50).");
  }
  if (draft.lettrage_escompte.trim().length > 120) {
    motifs.push("Lettrage / Escompte : 120 caractères au plus.");
  }
  return motifs;
}

const text = (value: string) => (value.trim() ? value.trim() : null);

export function draftToLigne(draft: LineDraft): LigneSoumise {
  return {
    numero: draft.numero,
    date_operation: text(draft.date_operation),
    date_valeur: text(draft.date_valeur),
    libelle: text(draft.libelle),
    reference: text(draft.reference),
    debit: draft.debit.trim() ? unsigned(draft.debit) : null,
    credit: draft.credit.trim() ? unsigned(draft.credit) : null,
    solde: draft.solde.trim() ? normalizeSignedAmountInput(draft.solde) : null,
    pointage_type_id: draft.pointage_type_id,
    lettrage_escompte: text(draft.lettrage_escompte),
    commentaire: text(draft.commentaire),
  };
}

export function sameDraft(a: LineDraft, b: LineDraft): boolean {
  return (Object.keys(a) as (keyof LineDraft)[]).every((key) => a[key] === b[key]);
}

/** « 12500.5 » → 1250050n. */
export function toCents(value: string): bigint {
  const negative = value.startsWith("-");
  const [whole, decimals = ""] = (negative ? value.slice(1) : value).split(".");
  const cents = BigInt(whole || "0") * 100n + BigInt((decimals + "00").slice(0, 2));
  return negative ? -cents : cents;
}

/** 1250050n → « 12500.50 ». */
export function fromCents(cents: bigint): string {
  const negative = cents < 0n;
  const absolute = negative ? -cents : cents;
  const whole = absolute / 100n;
  const rest = (absolute % 100n).toString().padStart(2, "0");
  return `${negative ? "-" : ""}${whole}.${rest}`;
}

export function summariseDrafts(
  drafts: LineDraft[],
  fileOpening: string | null,
  fileClosing: string | null,
): DraftSummary {
  const lines = drafts.map(draftToLigne);
  const debits = lines.map((line) => toCents(line.debit ?? "0"));
  const credits = lines.map((line) => toCents(line.credit ?? "0"));
  const sum = (values: bigint[]) => values.reduce((total, value) => total + value, 0n);
  const dates = lines.map((line) => line.date_operation).filter((d): d is string => !!d).sort();
  const result: DraftSummary = {
    count: lines.length,
    totalDebit: fromCents(sum(debits)),
    totalCredit: fromCents(sum(credits)),
    periodeDebut: dates[0] ?? null,
    periodeFin: dates.at(-1) ?? null,
    ouverture: fileOpening,
    cloture: fileClosing,
    coherent: null,
  };
  if (lines.length === 0) return result;
  // Même lecture que le serveur : ordre du fichier, inversé s'il va du plus récent au plus ancien
  const indexes = lines.map((_, index) => index);
  const first = lines[0].date_operation ?? "";
  const last = lines.at(-1)?.date_operation ?? "";
  const ordered = first > last ? indexes.reverse() : indexes;
  const allSoldes = lines.every((line) => line.solde !== null);
  if (allSoldes) {
    const head = ordered[0];
    const tail = ordered.at(-1) as number;
    result.ouverture ??= fromCents(toCents(lines[head].solde as string) - credits[head] + debits[head]);
    result.cloture ??= lines[tail].solde;
  }
  if (result.ouverture !== null && result.cloture !== null) {
    const movements = sum(credits) - sum(debits);
    result.coherent = toCents(result.ouverture) + movements === toCents(result.cloture);
  }
  return result;
}
```

- [ ] **Step 4: Run, expect PASS** — `npx vitest run lib/statementLines.test.ts && npm run lint && npm run typecheck`.

- [ ] **Step 5:** `git status`.

---

### Task 7: aperçu modifiable dans l'assistant d'import

**Files:**
- Create: `frontend/components/releves/EditablePreview.tsx`
- Modify: `frontend/components/releves/ImportWizard.tsx`

**Interfaces:**
- Consumes: Task 5 (`listPointageTypes`, `ConfirmOptions` avec `lignes`), Task 6 (`LineDraft`, `draftFromLine`, `checkDraft`, `draftToLigne`, `sameDraft`, `summariseDrafts`), `businessToday()` (`lib/balances`), `StatusBadge`, `DateInput`, `TextInput`, `NumberInput`, `Select` (`components/ui/Field`).
- Produces: `<EditablePreview analysis pointages drafts originals checked editing onChange onToggle onEdit onReset />` (contrôlé par l'assistant) ; l'assistant envoie `confirmStatement(request, { lignes: checkedDrafts.map(draftToLigne) })`.

- [ ] **Step 1:** charger le skill `simtis-design` ; relire `components/releves/ImportWizard.tsx` (étape Validation actuelle).

- [ ] **Step 2: Implement l'état dans `ImportWizard`**

À la réception d'une analyse sans erreur de mapping (`run`) :

```ts
      const originals = result.lignes.map(draftFromLine);
      setOriginals(originals);
      setDrafts(originals);
      // Cochées par défaut : lignes valides ; jamais une ligne déjà importée
      setChecked(new Set(result.lignes.filter((line) => line.statut === "Valide").map((l) => l.numero)));
      setEditing(null);
```

Chargement des Pointages une fois (`useEffect` sur `listPointageTypes()`, `.then`, liste vide si échec). Supprimer les états `keep`, `ecarter`, `filter` (le filtre d'affichage reste possible mais n'est plus requis ; le retirer pour simplifier). Calculs dérivés :

```ts
  const today = businessToday();
  const lineByNumber = new Map(analysis?.lignes.map((line) => [line.numero, line]) ?? []);
  const motifsOf = (draft: LineDraft) => checkDraft(draft, today);
  const checkedDrafts = drafts.filter((draft) => checked.has(draft.numero));
  const summary = summariseDrafts(
    checkedDrafts,
    analysis?.resume.solde_ouverture_fichier ? analysis.resume.solde_ouverture : null,
    analysis?.resume.solde_cloture_fichier ? analysis.resume.solde_cloture : null,
  );
  const blocked =
    !!analysis?.deja_importe ||
    checkedDrafts.length === 0 ||
    checkedDrafts.some((draft) => motifsOf(draft).length > 0);
```

Modification d'une cellule : remplacer le brouillon ; si la ligne d'origine était en erreur et que la ligne n'a plus de motif, l'ajouter à `checked` (règle « une ligne en erreur corrigée se coche automatiquement »). Confirmation :

```ts
        await confirmStatement(
          { file, accountId: account.id, mapping, feuille },
          { lignes: checkedDrafts.map(draftToLigne) },
        ),
```

- [ ] **Step 3: Implement `EditablePreview`** — tableau (pas `DataTable` : cellules éditables) dans un conteneur `overflow-x-auto rounded-[12px] border border-simtis-border`, en-tête `bg-simtis-light/60 text-[13px] font-semibold text-simtis-primary-dark`. Colonnes : Importer (case, `aria-label="Importer la ligne N"`, désactivée si déjà importée) · État (badge `StatusBadge` Valide / Erreur / Doublon calculé : motifs → Erreur ; ligne d'origine Doublon → Doublon ; sinon Valide ; mention « corrigée » `text-xs text-simtis-primary` si `!sameDraft(draft, original)`) · Société · Pointage · Banque · Date d'opération · Date de valeur · Libellé (+ référence) · Débit · Crédit · Solde · Lettrage / Escompte · Commentaire · action. Ligne en lecture : textes formatés (`formatDate`, `formatAmount(draftToLigne(draft).debit, suffix, { dashForZero: true })`) ; bouton icône `PenLine` « Modifier la ligne N ». Ligne en édition (`editing === numero`) : `DateInput` (dates), `TextInput` (libellé, référence, lettrage, commentaire), `NumberInput` (débit, crédit, solde), `Select` (Pointage, placeholder « Automatique »), puis boutons « Terminer » (`Check`) et « Annuler les corrections » (`RotateCcw`, rend `originals`). Sous la ligne en édition, ses motifs en `text-simtis-danger-fg`. Société / Banque : `account.company` non disponible dans `Analysis` → afficher `analysis.bank_code` (BankLabel) et la société active via `useCompany()` dans l'assistant, passée en prop `societe`.
Résumé au-dessus du tableau : les 4 tuiles deviennent « Lignes à importer » (count), « Lignes en erreur » (cochées avec motifs), « Doublons » (lignes d'origine Doublon), « Lignes ignorées » (`resume.nb_ignorees`) ; période, totaux, soldes depuis `summary` ; alerte warning si `summary.coherent === false`.

- [ ] **Step 4: Verify** — `npm run lint && npm run format:check && npm run typecheck && npm test`.

- [ ] **Step 5:** `git status`.

---

### Task 8: modification après l'import (relevé continu)

**Files:**
- Create: `frontend/components/releves/TransactionEditModal.tsx`
- Modify: `frontend/components/releves/AccountStatementCard.tsx`, `frontend/components/releves/RelevesView.tsx` (passer `canEdit`)

**Interfaces:**
- Consumes: `updateTransaction`, `listPointageTypes` (Task 5), `FormModal`, `Field`, `Select`, `TextInput`.
- Produces: `<TransactionEditModal transaction pointages onClose onSaved(updated: Transaction) />`.

- [ ] **Step 1: Implement la fenêtre** — `FormModal` titre « Modifier l'opération du JJ/MM/AAAA » ; en lecture (`dl`) : date, libellé, débit, crédit, solde ; champs : Pointage (`Select`, options des types actifs, `placeholder="Aucun"`), Lettrage / Escompte (`TextInput`, `maxLength={120}`), Commentaire (`TextInput`, `maxLength={1000}`). À l'envoi : `updateTransaction(transaction.id, { pointage_type_id, lettrage_escompte: text || null, commentaire: text || null })` ; erreur API affichée dans la fenêtre ; succès → `onSaved(updated)` + toast « Opération modifiée. ».

- [ ] **Step 2: Implement dans `AccountStatementCard`** — prop `canEdit: boolean` (depuis `RelevesView` : `hasAnyPermission(user.permissions, [PERMISSIONS.STATEMENTS_IMPORT])`) ; colonne « Actions » ajoutée seulement si `canEdit`, bouton icône `PenLine` « Modifier l'opération du JJ/MM/AAAA {libellé} » ; à l'enregistrement, remplacer la ligne dans `data.operations` sans recharger. Dans la cellule Libellé, sous la référence : `{row.origine === "Corrigée" && <span className="block text-xs text-simtis-primary">corrigée avant l'import</span>}`. Charger les Pointages une fois (`listPointageTypes`).

- [ ] **Step 3: Verify** — `npm run lint && npm run format:check && npm run typecheck && npm test && npm run build`.

- [ ] **Step 4:** `git status`.

---

### Task 9: contrôle dans Edge, documentation

**Files:**
- Modify: `CLAUDE.md`, `docs/specs/Plan_Phases_Realisation_SIMTIS.md`, `.claude/skills/simtis-design/pages.md`
- Script temporaire (scratchpad, jamais dans le dépôt) : `e2e/modifiable.mjs`

- [ ] **Step 1:** `docker compose restart backend` (applique 0006) ; vérifier `alembic_version = 0006`.
- [ ] **Step 2: Script Edge** (Société X / BP, Trésorerie puis Direction) : fichier avec SOLDE INITIAL et une ligne « montant illisible » → la ligne est Erreur et décochée ; « Modifier » → saisir `12 500,50` → la ligne devient Valide et se coche, mention « corrigée » ; « Annuler les corrections » → retour à Erreur ; corriger à nouveau ; décocher une autre ligne → résumé recalculé (nombre, totaux) ; aucun bouton « Ajouter » ; « Confirmer l'import » → relevé continu avec mention « corrigée » ; « Modifier l'opération » → Pointage Frais bancaires + commentaire → valeurs affichées ; Direction : aucune icône Modifier ; mobile 390 px sans débordement ; aucune erreur JavaScript.
- [ ] **Step 3:** nettoyer en base les seules données Société X / BP créées par le script (import, relevé, opérations, solde « Relevé » du jour de clôture, contrôle, modèle de colonnes BP créé), comme les contrôles précédents.
- [ ] **Step 4: Docs** — `CLAUDE.md` (état actuel : aperçu modifiable, `lignes`, `origine`, `PATCH`, `GET /api/pointage-types`) ; plan de phases (paragraphe « Relevés modifiables — réalisé le … ») ; `pages.md` (étape Validation modifiable, fenêtre de modification, mention « corrigée »).
- [ ] **Step 5: Vérification finale** — backend : `ruff check .`, `ruff format --check .`, `pytest`, `alembic check` ; frontend : `npm run lint && npm run format:check && npm run typecheck && npm test && npm run build`. `git status`.
