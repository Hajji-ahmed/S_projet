# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

The technical foundation (phase P3) is in place: `docker compose up --build` starts PostgreSQL, FastAPI (`backend/`) and Next.js (`frontend/`). The backend only exposes `GET /api/health`. The frontend has the layout (sidebar + header), the 13 routes as empty pages, and 11 Design System components shown on `/design-system`. There are no database tables, migrations or authentication yet (P4 and P5). Specification documents are in `docs/specs/`, the project skills in `.claude/skills/`. See `README.md` for the URLs and troubleshooting.

The project language is **French**: the UI labels, the domain terms and all documentation. Keep domain terms in French in the code and UI (Rapprochement, Écart, Position disponible…).

## Commands

```bash
docker compose up --build                                  # start everything (no .env needed)
docker compose up -d --wait                                # start in the background, wait until healthy

# Backend (in the container; tests need the db, started automatically)
docker compose run --rm backend ruff check .
docker compose run --rm backend ruff format --check .      # drop --check to apply
docker compose run --rm backend pytest
docker compose run --rm backend pytest tests/test_health.py::test_health_ok_when_database_reachable
docker compose run --rm backend alembic upgrade head

# Frontend (from frontend/, Node 22+)
npm run lint && npm run format:check && npm run typecheck && npm test && npm run build
npx vitest run lib/format.test.ts                          # a single test file
```

CI (`.github/workflows/ci.yml`) runs the same checks. Every command above must pass before a task is reported done.

Environment notes:
- The frontend dev server runs with `next dev --webpack` and file polling. Turbopack does not see file changes on bind mounts from Windows, so hot reload silently breaks with it.
- The database is published on host port **5434** (5432 and 5433 are commonly taken). Containers reach it at `db:5432`.
- A new API router must be added in `backend/app/api/router.py`. A new ORM model must be imported in `backend/app/models/__init__.py`, otherwise Alembic will not see it.
- Colours live in `frontend/app/globals.css`, mirrored in `.claude/skills/simtis-design/tokens.css`. Keep both in sync. `formatAmount()` in `frontend/lib/format.ts` formats every displayed amount and never truncates.

## What SIMTIS is

SIMTIS Finance is a treasury and bank-reconciliation platform. It replaces manual Excel work done by the Treasury team (Salma, bank position) and the Accounting team (Mustapha, reconciliation). It is an **integration, control and reporting layer**. It must **not** become a second Sage: accounting entries are imported from Sage / SI, never re-created.

Data flow: `Banks / Sage-SI / Excel-CSV → Import → Column mapping + checks → Normalisation → Position / Reconciliation / Forecasts → Discrepancies → Dashboard`.

## Source documents: which one wins

| Document (in `docs/specs/`) | Authority |
|---|---|
| `Cahier_des_charges_SIMTIS_V3_*.pdf` | Scope, data model, formulas, statuses, acceptance criteria |
| `Architecture_fonctionnelle_detaillee_SIMTIS.pdf` | Business flows, modules, user roles |
| `Architecture_technique_detaillee_SIMTIS.pdf` | Stack, folder layout, services, tables, security |
| `Remarque_modification_3_tableaux_SIMTIS.md` + `SIMTIS_3_tableaux_corriges(1).xlsx` | **Exact display structure** of the Banques, Devises and Prévisions tables. It overrides the CDC for display only. |
| `Prompt_Design_SIMTIS_Claude.md` + dashboard PNG | UI/UX. Condensed into the `simtis-design` skill. |
| `Plan_Phases_Realisation_SIMTIS.md` | Consolidated delivery plan (phases P0–P20), DB tables, API endpoints, open questions. Use it instead of the older `README_Phases_Realisation_Projet_SIMTIS.md`, whose phase numbering is inconsistent. |

## Architecture

- **Stack**: Next.js (App Router, TypeScript, Tailwind) → HTTPS/REST → FastAPI → PostgreSQL, run with Docker Compose (`frontend`, `backend`, `db`). Redis or a worker only if imports become heavy; it is not part of the MVP.
- **The frontend never talks to PostgreSQL.** Every call goes through FastAPI, via an API client in `frontend/lib/` and wrappers in `frontend/services/`.
- **Backend layering**: `api/` (thin endpoints) → `services/` (all business rules) → `repositories/` (DB access) → `models/` (ORM). Pydantic `schemas/` validate input and output. Endpoints must not contain business logic.
- **Services**: Bank, Import, Normalization, Position, Reconciliation, Forecast, Audit.
- **Core relations**: Bank 1→N Account 1→N Statement 1→N Transaction. Transaction N↔N AccountingEntry through `reconciliation_matches`, which covers the 1→1, 1→N, N→1 and N→N cases.
- **Imports are two-step**: analyse and preview first (detected columns, mapping, valid / error / duplicate rows), then the user confirms. Bank and Sage imports share the same pipeline.
- **Security**: JWT, then role, then permission, checked in the backend before every sensitive operation (import, validation, reconciliation, modification, admin). Roles: Administrateur, Trésorerie, Comptable, Responsable, Direction/Consultation, Personnalisé.
- **Audit**: every sensitive action writes to `audit_logs` with the user, the timestamp and the old and new values.

## Domain rules that code must respect

```text
Crédit disponible       = Crédit autorisé − Crédit utilisé
Position disponible     = Solde bancaire + Crédit disponible
Disposition FC réel     = Solde bancaire + Crédit autorisé
Position prévisionnelle = Position de départ + Encaissements prévus − Décaissements prévus   (cascades day to day)
```

- Money is `NUMERIC(18,2)` in the database and `Decimal` in Python, never `float`.
- Never sum different currencies directly. A MAD conversion always stores the rate and the rate date.
- The reconciliation engine only **proposes** matches, using a score built from reference, amount, date, label and third party. A human with the right permission validates each one. Never auto-validate on amount alone, and never when several candidates are close.
- Statuses:
  - Reconciliation: Rapprochée / À vérifier / Non rapprochée / Écart.
  - Écarts: À traiter → En cours → Traité → Clôturé. Closing requires a comment.
  - Forecasts: Prévu / En attente / Réalisé / Reporté / Annulé.
- **Decided terms** (section 3.3 of `Plan_Phases_Realisation_SIMTIS.md`): Taux = interest rate; Ligne = Crédit autorisé, shown as "Crédit autorisé" in the Banques table until the business gives the final label; Date (Banques table) = date of last update; Pointage = operation type (encaissement, décaissement, frais bancaires…), not a reconciliation status; bank statements are Excel only; Sage/SI comes in as a file export; the bank is labelled "Attijariwafa" (not Tijari); "UAR" = EUR and is shown as "EUR". Crédit utilisé and exchange rates are entered by hand (form + audit), not imported.
- **Two companies**: Simtis and a second one shown as "Société X" until its name is confirmed. A `companies` table is required. Positions are shown per company, never consolidated. Each company has its own accounting export, and reconciliation never matches across companies.
- **Unresolved terms**: the business still has to define Dépassement, Lettrage/Escompte and compte RH convertible. Do not invent their meaning or "fix" these labels. Ask. The team will send complete versions of the Prévisions, Devises and Banques tables; until then their exact structure is open (section 3.4 of the plan).
- **Logos**: `frontend/public/logo-simtis.png` and `frontend/public/banques/{cih,attijariwafa,bp,bmce}.png`.

## How to work on a task

Before any task that creates or changes an application file (code, configuration, migrations, tests, dependencies, Docker, CI), load the **`simtis-plan`** skill. Present the implementation plan, end the turn, and wait for the user's explicit confirmation before writing anything. For this project it replaces the superpowers brainstorming and writing-plans workflows. Updating the project documentation (`*.md`, skills) does not need a plan.

## UI work

Load the **`simtis-design`** skill before any frontend page, component or styling work. It holds the tokens, components, per-page specs and the three imposed table layouts. Its rules:

- Design tasks change visuals only: no API, route, calculation or business-logic changes.
- Use the teal palette via tokens only.
- Use Lucide icons, no emoji.
- Use the real SIMTIS logo file, never a re-drawn one.
