# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

Done: P3 (technical foundation), P4 (database), P5 (authentication, roles, permissions, audit), P6 (banks, accounts and active company, daily balances), P7 (statement import), P8.1 + P8.3 (Banques table and chart; P8.2 dropped by the business), P10 (Sage import), P11 (reconciliation 1 → 1 and N → 1 groups), P13 (manual 1-N / N-1 / N-N matches; automatic 1 → N not built), P15 (dashboard), P16 (administration, history, settings, reports). P12 Écarts was removed from the code on 04/11/2026 (migration 0046; history in `docs/decisions/ecarts.md`). Not yet: P9 / P14 (the Devises and Prévisions tables of `/position-bancaire` are entered by hand, nothing in them is computed), PDF reports other than the position.

`docker compose up --build` starts PostgreSQL, FastAPI (`backend/`) and Next.js (`frontend/`). On every start the backend applies the Alembic migrations and loads the reference seeds before serving the API. Data model: `docs/modele-donnees.md`.

**Detailed decisions live in `docs/decisions/`**, one file per module: every business decision with its date, migration, functions, API routes, screens and measured volumes, in the order it was taken (a later paragraph may replace an earlier one). **Before working on a module, read its file.** When a decision is added or changed, write it there (last paragraph, saying what it replaces) and touch this file only for a rule that crosses modules.

| Module | File | Main code |
|---|---|---|
| Position bancaire (Banques, Prévisions, Devises, chart) | `docs/decisions/position-bancaire.md` | `position_service`, `position_banques_service`, `components/position/` |
| Statements: import, pointage, balances, PDF | `docs/decisions/releves.md` | `import_service`, `import_file`, `normalization_service`, `/releves` |
| Pending operations « (*) » and separate files | `docs/decisions/operations-en-cours.md` | `import_service`, `position_repository.en_cours_hors_releve` |
| Sage entries, accounting balance, due dates | `docs/decisions/ecritures-sage.md` | `accounting_import_service`, `solde_comptable_service`, `echeance_service`, `/ecritures` |
| Manual lines, import deletion, Excel reprise | `docs/decisions/saisies-suppressions-reprises.md` | `saisie_manuelle_service`, `suppression_import_service`, `reprise_service` |
| Reconciliation engine (score, types, groups, codes) | `docs/decisions/rapprochement-moteur.md` | `reconciliation_scoring`, `reconciliation_groupes`, `reconciliation_service` |
| Reconciliation screen (panes, proposals, ambiguous, batches) | `docs/decisions/rapprochement-ecran.md` | `components/rapprochement/`, `lib/reconciliation.ts` |
| Bank fees booked by SIMTIS, « À comptabiliser » | `docs/decisions/frais-bancaires.md` | `frais_service`, `frais_repository`, `FraisCard` |
| Écarts (removed on 04/11/2026) | `docs/decisions/ecarts.md` | none |
| Accounts screen | `docs/decisions/comptes.md` | `account_service` |
| Dashboard | `docs/decisions/dashboard.md` | `dashboard_service`, `components/dashboard/` |
| Administration, history, settings, reports | `docs/decisions/administration-rapports.md` | `admin_service`, `historique_service`, `parametres_service`, `rapports_service` |

Specs written before building: `docs/superpowers/specs/`.

Rules that cross modules (details in the files above):
- **Imports are two-step** (analyse, then confirm with the lines the user checked), statements and Sage share `services/import_file.py`; `.xlsx`, `.xls`, and PDF for statements; up to 50 000 lines / 20 Mo. A line already in the database is a duplicate (line hash); identical lines of one file are two real operations.
- **One continuous statement per account**, read and exported in the 11-field standard format (`import_service.STANDARD_HEADERS`). Operations are ordered by date, statement, then `bank_transactions.ordre` (`import_repository.ORDRE_CHRONOLOGIQUE`), never by id.
- **Reconciliation**: the engine only proposes; it compares two lines of the same company and bank account, opposite sign, exactly the same amount (`montant_rapprochement`: the currency amount for EUR / USD) and the same operation type; a human validates, and every validated match gets a code « BANQUE-AA-NNNNNN ». Lines in proposal are « À vérifier » in the database but shown « Non rapprochée ». Bank fees are never matched alone, except against a Sage fee entry of the same amount (INTERET, AGIOS, COM…, since 05/11/2026): SIMTIS books them (`frais_service`) and they show in « À comptabiliser ». Pending operations « (*) » are never reconciled.
- **Production data operations** (reprises of BP on 27/10/2026 and BMCE on 30/10/2026, BP labels on 28/10/2026, lifted rejections on 28/10/2026) are recorded in their module file with their backup. Always: backup, simulation without `--appliquer`, then `--appliquer` with a motif.

General notes:
- The sidebar can be collapsed to icons on large screens (button at its bottom, `lib/sidebar.ts` with `useSyncExternalStore`, choice kept in `localStorage` key `simtis.menu.reduit`, session-only when storage is unavailable).
- Time zone: tzdata 2026c (Python in the container, Edge) puts Africa/Casablanca at UTC+0 in October 2026, the local Node (tzdata 2025c) at UTC+1; never write a test whose result depends on Morocco's 2026 offset.
- Value parsing (dates, amounts, labels, references, hashes) lives in `normalization_service.py` as pure functions, shared by the statement and Sage imports.
- The header holds the active company (`useCompany()` in `frontend/components/company/CompanyProvider.tsx`); every company-scoped screen reads it and never mixes companies.
- The frontend has `/login`, the layout (sidebar filtered by permissions, header with the real user and logout), the 11 routes (the empty `/previsions` and `/devises` pages were removed on 05/10/2026: the Prévisions and Devises tables live on `/position-bancaire`, so P9 and P14 will build there, not on separate pages), and 11 Design System components shown on `/design-system`.
- Accounts: see "Connexion" in `README.md` (demo accounts with `python -m app.seeds --demo`, real ones with `python -m app.cli create-user`). Specification documents are in `docs/specs/`, the project skills in `.claude/skills/`. See `README.md` for the URLs and troubleshooting.

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
docker compose run --rm backend alembic upgrade head      # also done at startup
docker compose run --rm backend alembic revision --autogenerate -m "..."   # then READ the result
docker compose run --rm backend python -m app.seeds        # reference data, also done at startup
docker compose run --rm backend python -m app.seeds --demo # demo data marked DEMO, refused when APP_ENV=production

# Frontend (from frontend/, Node 22+)
npm run lint && npm run format:check && npm run typecheck && npm test && npm run build
npx vitest run lib/format.test.ts                          # a single test file
```

CI (`.github/workflows/ci.yml`) runs the same checks. Every command above must pass before a task is reported done.

Environment notes:
- The frontend dev server runs with `next dev --webpack` and file polling. Turbopack does not see file changes on bind mounts from Windows, so hot reload silently breaks with it.
- **Local network access** (phone through the PC's hotspot, another PC; 09/10/2026): off by default. `.env` sets `BIND_ADDRESS=0.0.0.0` (ports 3000 and 8000; the database stays on 127.0.0.1), `CORS_ORIGIN_REGEX` (extra allowed origins, `allow_origin_regex`) and `ALLOWED_DEV_ORIGINS` (this PC's IPs, read by `next.config.ts`, which Next.js 16 needs in dev). `NEXT_PUBLIC_API_URL` is empty by default: the browser calls the API on the page's own host, port 8000 (`apiUrlFor` in `frontend/lib/api.ts`). Windows needs a firewall rule for 3000/8000 on the Private profile (see README « Accès depuis le réseau local »). Backend tests inherit `.env`: a test that needs the default CORS must clear `CORS_ORIGIN_REGEX`.
- **Production** (22/10/2026, server 10.77.77.11, folder `~/simtis`): `docker-compose.prod.yml` with `backend/Dockerfile.prod` (no dev deps, non-root, 2 uvicorn workers, `--proxy-headers` so `client_ip` reads Caddy's X-Forwarded-For), `frontend/Dockerfile.prod` (`next build --webpack`: Turbopack panicked internally on the server on 23/10/2026; test files are removed before the build, `output: "standalone"`, `NEXT_PUBLIC_API_URL=/api` at build time, same origin) and Caddy (`deploy/Caddyfile`, `tls internal` with `default_sni` for an IP address, `/api/*` to the backend with 100 MB bodies and 10 min timeouts, the rest to the frontend); only 80/443 are published; same project name and `db_data` volume as dev. `.env` needs `SITE_ADDRESS`, `CORS_ORIGINS=https://…`, strong `POSTGRES_PASSWORD` / `JWT_SECRET`. Each PC trusts Caddy's root certificate (`caddy_data` volume, README « Mise en production »). Nightly backup: `~/sauvegarde-simtis.sh` (crontab 2 h, `~/backups`, 30 days). **Since 22/10/2026 the server runs in HTTP only** until a domain name is bought: `.env` has `CADDYFILE=Caddyfile.http` (`deploy/Caddyfile.http`, port 80, same routes, no TLS), `APP_ENV=development` (the session cookie would be « Secure » in production and the browser would drop it over HTTP) and `CORS_ORIGINS=http://10.77.77.11`; address `http://10.77.77.11`, also `http://10.77.77.11:3000` (Caddy published on 3000 too). Going back to HTTPS = remove these three lines. **Automatic deployment** (23/10/2026, public repo): the server's `~/simtis` is a git clone of `hajji`; cron runs `bash ~/simtis/deploy/auto-deploy.sh` every 5 minutes: on a new commit whose GitHub check-runs are all green (read with the token of `~/.simtis-github-token`, « Checks : Read-only », if present; the code comes through the read-only deploy key `~/.ssh/simtis_deploy`, so the repository can be private), it backs up, `git reset --hard`, `docker compose -f docker-compose.prod.yml up -d --build --wait`, checks `/api/health`, logs to `~/backups/deploiement.log`; a red or failed commit is recorded in `.deploiement-echoue` and not retried (no self-hosted runner). Never edit code on the server. Never run `docker compose down -v`.
- The database is published on host port **5434** (5432 and 5433 are commonly taken). Containers reach it at `db:5432`.
- A new API router must be added in `backend/app/api/router.py`. A new ORM model must be imported in `backend/app/models/__init__.py`, otherwise Alembic will not see it.
- Backend tests run on a dedicated database `simtis_test`, created and migrated by `tests/conftest.py` (so they exercise the real migration) and dropped at the end. Each test runs in a transaction rolled back afterwards. Provoke expected constraint failures with `assert_rejected` from `tests/helpers.py`, never with a bare `session.rollback()`, which would also undo the test's own setup data.
- `alembic check` (and `test_migration_matches_models`) does **not** compare CHECK constraints. Every new CHECK, UNIQUE or trigger needs its own test in `tests/test_constraints.py`, written to fail when the rule is removed.
- Autogenerated migrations must be read before being applied: they miss triggers and functions (see the `audit_logs` trigger in migration 0001). `audit_logs` is append-only at the database level.
- Seeds only create, never update or delete, so a value changed by a user (for example a company name) survives a restart. Role permissions are applied only when a role is created.
- Colours live in `frontend/app/globals.css`, mirrored in `.claude/skills/simtis-design/tokens.css`. Keep both in sync. **Visual refresh « SaaS FinTech »** (14/10/2026, visual only; **its colours were reverted on 15/10/2026** at the business's request: every token is back to the original teal palette, `--simtis-sidebar` = #004F54 and `--simtis-surface` = #F5F8FA stay as aliases in that palette, `info` and `violet` stay for the dashboard KPI tiles, and tables are back to their teal-light header with teal-dark text; the shapes, shadows, focus ring and layouts are kept): new tokens `sidebar`, `surface`, `info` / `info-bg` / `info-fg`, `rounded-card` (16 px) and `shadow-simtis-hover`; global turquoise `:focus-visible`, Recharts tooltip style and `prefers-reduced-motion` in `globals.css`. Shared components (`Card`, `KpiCard`, `Button`, `Field`, `DataTable`, `Modal`, `StatusBadge` with a dot, `EmptyState`…), the sidebar (logo on its original white tile, active item filled), the header (translucent, round bell and avatar) and the dashboard cards follow it. `formatAmount()` in `frontend/lib/format.ts` formats every displayed amount and never truncates. **Layout fixes of 21/10/2026** (visual only): chart axes and the donut centre use `formatCompact()` (« 18 M », « 840 k DH », non-breaking spaces because Recharts wraps a tick at every space; exact amount in the tooltip / `title`); the Banques, Devises and Prévisions tables get a minimum width of `LARGEUR_BANQUE` (150 px) per bank column (`largeurMin` in `components/position/GridCell.tsx`) and scroll inside their frame; the /rapprochement grid has an explicit `grid-cols-[minmax(0,1fr)]` below xl (an implicit grid track grew to the width of the tables and made the whole page scroll sideways); `Card` headers wrap; `DataTable` columns can be `sticky` (Comptes « Actions » stays visible on the right); the statement and Comptes labels have a minimum width; on the dashboard « Rapprochement par banque » spans both columns at 2 columns; the « Solde total banques » tile says « Comptes MAD (hors EUR / USD) »; the header's global search is hidden until it is built (`SearchBar` kept, unused).

## What SIMTIS is

SIMTIS Finance is a treasury and bank-reconciliation platform. It replaces manual Excel work done by the Treasury team (Salma, bank position) and the Accounting team (Mustapha, reconciliation). It is an **integration, control and reporting layer**. It must **not** become a second Sage: accounting entries are imported from Sage / SI, never re-created.

Data flow: `Banks / Sage-SI / Excel-CSV → Import → Column mapping + checks → Normalisation → Position / Reconciliation / Forecasts → Dashboard`.

## Source documents: which one wins

| Document (in `docs/specs/`) | Authority |
|---|---|
| `Cahier_des_charges_SIMTIS_V3_*.pdf` | Scope, data model, formulas, statuses, acceptance criteria |
| `Architecture_fonctionnelle_detaillee_SIMTIS.pdf` | Business flows, modules, user roles |
| `Architecture_technique_detaillee_SIMTIS.pdf` | Stack, folder layout, services, tables, security |
| `SIMTIS_tableaux_complets.xlsx` | **Exact display structure** of the Banques, Devises and Prévisions tables (one sheet, the three tables stacked on shared bank columns). It overrides the CDC for display only. Described in the `simtis-design` skill (`pages.md`). |
| `Remarque_modification_3_tableaux_SIMTIS.md` + `SIMTIS_3_tableaux_corriges(1).xlsx` | **Superseded** by `SIMTIS_tableaux_complets.xlsx`. Its general rule still applies: never redesign, rename, add, remove or move columns of the three tables, and never turn them into cards or charts. |
| `Prompt_Design_SIMTIS_Claude.md` + dashboard PNG | UI/UX. Condensed into the `simtis-design` skill. |
| `Plan_Phases_Realisation_SIMTIS.md` | Consolidated delivery plan (phases P0–P20), DB tables, API endpoints, open questions. Use it instead of the older `README_Phases_Realisation_Projet_SIMTIS.md`, whose phase numbering is inconsistent. |
| `docs/Cahier_des_charges_SIMTIS_V4.pdf`, `docs/Architecture_fonctionnelle_SIMTIS_V2.pdf`, `docs/Architecture_technique_SIMTIS_V2.pdf` (21/10/2026) | Updated versions for the business, describing what is decided and built, with the open questions. Generated from `docs/sources/*.html` by `docs/sources/generer-pdf.ps1` (Edge headless). They summarise this file; the originals in `docs/specs/` keep their authority for the initial scope. |

## Architecture

- **Stack**: Next.js (App Router, TypeScript, Tailwind) → HTTPS/REST → FastAPI → PostgreSQL, run with Docker Compose (`frontend`, `backend`, `db`). Redis or a worker only if imports become heavy; it is not part of the MVP.
- **The frontend never talks to PostgreSQL.** Every call goes through FastAPI, via an API client in `frontend/lib/` and wrappers in `frontend/services/`.
- **Backend layering**: `api/` (thin endpoints) → `services/` (all business rules) → `repositories/` (DB access) → `models/` (ORM). Pydantic `schemas/` validate input and output. Endpoints must not contain business logic.
- **Services**: Bank, Import, Normalization, Position, Reconciliation, Forecast, Audit.
- **Core relations**: Bank 1→N Account 1→N Statement 1→N Transaction. Transaction N↔N AccountingEntry through `reconciliation_matches`, which covers the 1→1, 1→N, N→1 and N→N cases.
- **Imports are two-step**: analyse and preview first (detected columns, mapping, valid / error / duplicate rows), then the user confirms. Bank and Sage imports share the same pipeline.
- **Security**: JWT, then role, then permission, checked in the backend before every sensitive operation (import, validation, reconciliation, modification, admin). Roles: Administrateur, Trésorerie, Comptable, Responsable, Direction/Consultation, Personnalisé.
- **Audit**: every sensitive action writes to `audit_logs` with the user, the timestamp and the old and new values.

## Security rules for new endpoints (P5)

- Add every new module router to `protected_router` in `backend/app/api/router.py`: it already requires a logged-in user (401). Never add a router to `public_router` without a reason; `tests/test_permissions.py` lists the public routes and fails on any other route that answers without a token.
- Every endpoint that reads or changes business data also takes `user: CurrentUser = Depends(require_permission(PermissionCode.X))` (403). Permission codes live in `backend/app/core/permissions.py`; `frontend/lib/permissions.ts` is a copy checked by a test, and `ROUTE_PERMISSIONS` there decides which pages the menu shows. Hiding a menu protects nothing: the API is the only real check.
- Permissions are never put in the JWT: they are reloaded from the database on every request, so a role change applies at once. The access token carries its session id; logout, password change and account deactivation cut access immediately.
- Services raise `NotFoundError` (404) or `ConflictError` (409) from `backend/app/services/errors.py` with a French message for the user; `app/main.py` turns them into `{"detail": message}`. Endpoints never build HTTP errors for business rules themselves. Input schemas use `extra="forbid"`, so a field that must not change (e.g. a bank `code`) gives 422 instead of being silently ignored.
- Accounts: **since 23/10/2026 a company may have several active accounts per (bank, currency, type)** (e.g. two BMCE USD; migration 0036 dropped the partial unique index `uq_bank_accounts_compte_actif_par_banque` of 0003; the account number stays unique and a Sage journal still belongs to one active account). The imposed tables keep one cell per bank and **add up** that bank's accounts of the cell's currency: `position_service.somme_soldes` (each day, the last known balance of each account that already has one; never 0 for an unknown one), `ligne_au` (LIGNE of the accounts that already have a balance), `CompteColonne` / `BanqueColonne.comptes`, `Cellule.detail` → API `detail` [{numero, solde}] shown as the cell's tooltip (`noteCellule` in `lib/position.ts`); the Taux row shows the rate only when all the bank's accounts share it; `bank_account_id` is the first account. The bank card adds up its MAD current accounts (`position_service.somme_figures`, `BankOut.nb_comptes_mad`), other accounts are listed with their number (`OtherAccountOut.numero`). Accounts are told apart on screen by `finNumero` (« …4521 », `lib/accounts.ts`: `AccountChipLabel`, the import picker, the bank card). Reconciliation codes « BANQUE-AA-NNNNNN » now use one counter per **company, bank and year** (`reconciliation_code_counters` PK, `next_code_number` reads the account's company and bank): with a counter per account, two accounts of one bank gave the same code, refused by the per-company unique index; the migration seeded the counters from the highest number already given. Company, bank and currency of an account are immutable; the interest rate is sent and shown in % (`taux_interet_pct`) but stored as a fraction. Money and rates travel as exact strings (`"500000.00"`); the frontend never converts them to float (`frontend/lib/accounts.ts`).
- **The statement is the source of truth** (decision of 08/10/2026): for an account with at least one imported operation carrying a balance (`position_repository.comptes_alimentes_par_releve`), the card « Solde », the Banques table (so « Disponible Fc reel ») and the bank detail all read the statement only: Solde = Disponible Fc reel = the statement's « Solde de clôture » (`dernier_solde_releve`, chronological order). Its entered balances (source « Saisie ») stay in the database but are ignored; entering a new balance on it is refused (409), only the crédit utilisé can still be entered (`FiguresOut.solde_releve`, the form disables the Solde field). Accounts without a statement (CIH, BMCI today) keep hand-entered balances.
- Figures (P6.3): `backend/app/services/position_service.py` holds the CDC formulas as pure `Decimal` functions (reuse them in P8, never re-implement). Each field uses its latest known value up to today (Morocco time, `business_today()`); a value never entered stays `null` and is never treated as 0. A bank card shows the company's MAD current account; other accounts are listed in their own currency, never summed. Entering a balance again for the same day corrects it (audit keeps the old values).
- Clock skew: access tokens are decoded with a 60 s leeway (`CLOCK_SKEW_SECONDS`). Docker Desktop's VM steps its clock back by ~26 s at times, which made freshly issued tokens look "issued in the future" (random 401s in tests).
- Bank `code` is immutable after creation: seeds find reference rows by code at every start, so a renamed code would be recreated. Same reasoning applies to any seeded code (companies, roles, categories).
- Write the audit entry with `audit_service.log(db, user_id=user.id, action=..., entite=..., entite_id=..., avant=..., apres=..., ip=client_ip(request))` in the same transaction as the change, then commit once. `audit_service` masks passwords and tokens and stores `Decimal` as exact text.
- Frontend: call the API only through `apiFetch` (`frontend/lib/api.ts`), which adds the bearer token, turns a 422 without a business message into « Requête refusée : données invalides. », refreshes once on a 401 and sends the user back to `/login` when the session is gone. The access token stays in memory only, never in `localStorage`; the session lives in an HttpOnly cookie restricted to `/api/auth`.

## Domain rules that code must respect

```text
Crédit disponible       = Crédit autorisé − Crédit utilisé
Position disponible     = Solde bancaire + Crédit disponible
facilité de caisse      = Solde du jour   (decision of 02/11/2026, « Solde + LIGNE » before; solde du jour = solde de la dernière opération importée ce jour-là,
                          sinon solde du jour saisi, sinon dernier connu; since 08/10/2026 an account with an imported statement ignores its entered balances)
                          DEPASSEMENT of a day = TOTAL of the balances + TOTAL of their LIGNES (negative = credit line exceeded)
Disponible Fc reel      = Solde du dernier jour + LIGNE   (Banques table, decision of 02/11/2026; replaces « facilité de caisse − LIGNE » of 03/10/2026)
                          TOTAL = sum of the banks; DEPASSEMENT = TOTAL
Position prévisionnelle = Position de départ + Encaissements prévus − Décaissements prévus   (cascades day to day)
```

- Money is `NUMERIC(18,2)` in the database and `Decimal` in Python, never `float`.
- Never sum different currencies directly. A MAD conversion always stores the rate and the rate date.
- The reconciliation engine only **proposes** matches, using a score built from reference, amount, date, label and third party. A human with the right permission validates each one. Never auto-validate on amount alone. Since 08/10/2026 a close (but lower) competitor no longer blocks the proposal: it is flagged « Concurrente proche » and never pre-checked; only a tie gives no proposal.
- Statuses:
  - Reconciliation: Rapprochée / À vérifier / Non rapprochée (« Écart » removed with the Écarts module on 04/11/2026, a departure from the CDC).
  - Forecasts: Prévu / En attente / Réalisé / Reporté / Annulé.
- **Decided terms** (section 3.3 of `Plan_Phases_Realisation_SIMTIS.md`): Taux = interest rate (shown as a %); LIGNE = Crédit autorisé, stored as `bank_accounts.credit_autorise` and labelled "LIGNE" in the Banques table; Pointage = operation type (encaissement, décaissement, frais bancaires…), not a reconciliation status; bank statements are Excel only; Sage/SI comes in as a file export; "UAR" = EUR. Crédit utilisé and exchange rates are entered by hand (form + audit), not imported.
- **Banks**: five, displayed by code in this order: AWB (Attijariwafa), BMCE, BP, CIH, BMCI (`banks.ordre_affichage`). The three tables use these bank columns plus TOTAL (and DEPASSEMENT for Banques).
- **Daily balances**: the Banques table shows "facilité de caisse" on 3 dates, so balances are a per-day history (`bank_account_balances`), not a single field on the account.
- **Forecasts** belong to a company and optionally to a bank. A forecast without a bank is an Encaissement / Escompte / Douane amount of the Prévisions block; since 03/10/2026 these are entered **per line** of the block (migration 0007: `saisies_previsions_jour.ligne`, earlier day-level values moved to line 1; `PUT /api/position/previsions` carries them in each `lignes[]` item). Each forecast carries its own direction (`sens`: Entrée / Sortie).
- **Two companies**: Simtis and **Tefil** (code `SOCX`; shown as "Société X" until its name was confirmed on 05/10/2026, migration 0009 renamed it; Tefil has no EUR / USD accounts, so no Devises table). A `companies` table is required. Positions are shown per company, never consolidated. Each company has its own accounting export, and reconciliation never matches across companies.
- **Banques table, decided on 02/10/2026** (section 3.3 of the plan): only each bank's **MAD current account** counts ("Exp DH convertible" stays in the Devises table, out of TOTAL and Disponible Fc reel). There is one « facilité de caisse » row **per day, without limit**, and each bank's cell = **that day's balance** (since 02/11/2026; balance + LIGNE before). For each date, **DEPASSEMENT = TOTAL of the balances + TOTAL of their LIGNES**, and Disponible Fc reel = last balance + LIGNE. Worked example: AWB LIGNE 500 000 and balance −200 000; BMCE LIGNE 300 000 and balance +100 000; day row TOTAL −100 000, DEPASSEMENT −100 000 + 800 000 = 700 000; Disponible Fc reel 300 000 and 400 000, TOTAL = DEPASSEMENT = 700 000. The « Évolution de la position » chart, the PDF and the Excel report follow (the chart now draws the TOTAL of the balances).
- **Unresolved terms** (section 3.4 of the plan): the business still has to confirm Lettrage/Escompte, what "Exp DH convertible" means (modelled as an account type `DH convertible` in MAD), and how the Prévisions block reads (column C = due date or label). Do not invent their meaning or "fix" these labels. Ask.
- **Logos**: `frontend/public/logo-simtis.png` and `frontend/public/banques/{attijariwafa,bmce,bp,cih,bmci}.png`. Every table that names a bank shows its logo next to the code through `components/banks/BankLabel.tsx` (stacked above the code in the column headers of the imposed tables; business decision of 02/10/2026).

## How to work on a task

Before any task that creates or changes an application file (code, configuration, migrations, tests, dependencies, Docker, CI), load the **`simtis-plan`** skill. Present the implementation plan, end the turn, and wait for the user's explicit confirmation before writing anything. For this project it replaces the superpowers brainstorming and writing-plans workflows. Updating the project documentation (`*.md`, skills) does not need a plan.

## UI work

Load the **`simtis-design`** skill before any frontend page, component or styling work. It holds the tokens, components, per-page specs and the three imposed table layouts. Its rules:

- Design tasks change visuals only: no API, route, calculation or business-logic changes.
- Use the teal palette via tokens only.
- Use Lucide icons, no emoji.
- Use the real SIMTIS logo file, never a re-drawn one.
