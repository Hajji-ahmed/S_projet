"""Infrastructure de tests : une base PostgreSQL dédiée, jamais la base de développement.

La base `simtis_test` est créée au premier test, migrée avec Alembic (donc les tests exercent la vraie
migration), puis supprimée à la fin. Chaque test s'exécute dans une transaction annulée à sa fin.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

from app.core.config import get_settings

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DATABASE = "simtis_test"


def database_url(database: str) -> URL:
    """Même serveur que DATABASE_URL, autre base."""
    return make_url(get_settings().database_url).set(database=database)


def alembic_config(database: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    url = database_url(database).render_as_string(hide_password=False)
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


@contextmanager
def temporary_database(name: str) -> Iterator[None]:
    """Crée une base vide pour la durée du bloc, puis la supprime (même en cas d'échec)."""
    admin = create_engine(database_url("postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        try:
            yield
        finally:
            with admin.connect() as connection:
                connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    finally:
        admin.dispose()


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    with temporary_database(TEST_DATABASE):
        command.upgrade(alembic_config(TEST_DATABASE), "head")
        test_engine = create_engine(database_url(TEST_DATABASE))
        yield test_engine
        test_engine.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    """Session dont tout le contenu est annulé à la fin du test.

    Les échecs de contrainte doivent être provoqués avec `assert_rejected` (points de sauvegarde) :
    un `rollback()` direct annulerait aussi les données préparées par le test.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", autoflush=False)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
