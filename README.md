# SIMTIS Finance

Plateforme de trésorerie et de rapprochement bancaire. Elle remplace le travail manuel sous Excel de la Trésorerie (position bancaire) et de la Comptabilité (rapprochement). SIMTIS importe, contrôle et présente les données : les écritures comptables restent dans Sage / SI.

Flux : `Banques / Sage-SI / Excel → Import → Mapping et contrôles → Normalisation → Position / Rapprochement / Prévisions → Écarts → Dashboard`

## Démarrage

Prérequis : [Docker Desktop](https://www.docker.com/products/docker-desktop/) lancé.

```bash
docker compose up --build
```

Aucun fichier `.env` n'est nécessaire : `docker-compose.yml` fournit des valeurs de développement par défaut. Pour les changer, copier `.env.example` en `.env`.

| Service | URL | Rôle |
|---|---|---|
| Frontend (Next.js) | http://localhost:3000 | Application |
| Design System | http://localhost:3000/design-system | Tous les composants et état de la connexion à l'API |
| API (FastAPI) | http://localhost:8000/docs | Documentation interactive de l'API |
| Santé de l'API | http://localhost:8000/api/health | `{"status":"ok","database":"ok"}` |
| PostgreSQL | `localhost:5434` | Base `simtis` (utilisateur `simtis`), pour DBeaver ou pgAdmin |

Le premier démarrage télécharge les images et installe les dépendances (plusieurs minutes). Les suivants prennent quelques secondes. Les ports ne sont ouverts que sur `127.0.0.1` (votre poste).

## Commandes courantes

```bash
docker compose up -d --wait        # démarrer en arrière-plan et attendre que tout soit sain
docker compose ps                  # état des services
docker compose logs -f backend     # suivre les journaux d'un service
docker compose down                # arrêter (les données PostgreSQL sont conservées)
docker compose down -v             # arrêter ET effacer la base et les modules Node du conteneur
```

**Backend** (dans le conteneur) :

```bash
docker compose run --rm backend ruff check .           # lint
docker compose run --rm backend ruff format .          # formatage
docker compose run --rm backend pytest                 # tests, sur une base dédiée `simtis_test` (la base de développement n'est jamais touchée)
docker compose run --rm backend alembic upgrade head   # appliquer les migrations (fait aussi au démarrage)
docker compose run --rm backend alembic downgrade base # tout défaire
docker compose run --rm backend alembic revision --autogenerate -m "description"   # à relire avant de l'appliquer
docker compose run --rm backend python -m app.seeds          # données de référence (fait aussi au démarrage)
docker compose run --rm backend python -m app.seeds --demo   # + données de démonstration, marquées DEMO (développement uniquement)
```

**Frontend** (depuis `frontend/`, avec Node 22 ou plus) :

```bash
npm install            # une fois, pour l'éditeur et les commandes ci-dessous
npm run lint
npm run format         # ou format:check
npm run typecheck
npm test
npm run build
```

## Structure

```text
backend/    FastAPI : api/ (endpoints minces) → services/ (règles métier) → repositories/ (base) → models/ (ORM)
frontend/   Next.js (App Router, TypeScript, Tailwind) : app/, components/, lib/, services/, hooks/, types/
docs/specs/ Cahier des charges, architectures, plan de phases, maquettes
docs/modele-donnees.md   Schéma de la base (25 tables), diagramme et correspondance avec les tableaux du classeur
.claude/    Skills du projet (simtis-plan, simtis-design)
```

Le frontend ne parle jamais à PostgreSQL : tout passe par l'API (`frontend/lib/api.ts`, puis `frontend/services/`). Le plan de réalisation complet est dans [docs/specs/Plan_Phases_Realisation_SIMTIS.md](docs/specs/Plan_Phases_Realisation_SIMTIS.md).

## Problèmes fréquents

- **« port is already allocated »** : un autre programme utilise le port. Changer `POSTGRES_HOST_PORT` dans `.env` (le 5432 est souvent pris par un PostgreSQL local), ou arrêter l'autre programme.
- **Une modification du frontend n'apparaît pas** : le rechargement à chaud utilise la scrutation des fichiers (mode webpack), avec quelques secondes de délai. Après un changement de `package.json` (nouvelle dépendance), le volume `node_modules` du conteneur ne se met pas à jour tout seul. Le recréer, sans toucher à la base :

  ```bash
  docker compose rm -sf frontend
  docker volume rm simtis-finance_frontend_node_modules
  docker compose up -d --build
  ```
- **Frontend plus rapide en local** : lancer seulement la base et l'API dans Docker, puis le frontend sur le poste.

  ```bash
  docker compose up -d --wait db backend
  cd frontend && npm install && npm run dev
  ```

## Conventions

- Langue du projet : français (interface, termes métier, documentation). Les termes métier restent en français dans le code.
- Montants : `NUMERIC(18,2)` en base, `Decimal` en Python, jamais `float`. Jamais de somme entre devises différentes.
- Couleurs : uniquement via les variables `--simtis-*` (voir `frontend/app/globals.css`).
- Secrets : jamais dans Git. `.env` est ignoré ; `.env.example` documente les variables.
