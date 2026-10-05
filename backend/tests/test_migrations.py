"""Les migrations Alembic : créer, défaire, refaire, et rester identiques aux modèles."""

from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect, text

from app.models import Base
from app.services.normalization_service import line_hash
from tests.conftest import alembic_config, database_url, temporary_database

D = Decimal

MIGRATION_DATABASE = "simtis_test_migrations"


@pytest.fixture
def empty_database() -> Iterator[tuple[Config, Engine]]:
    with temporary_database(MIGRATION_DATABASE):
        engine = create_engine(database_url(MIGRATION_DATABASE))
        yield alembic_config(MIGRATION_DATABASE), engine
        engine.dispose()


def user_tables(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names()) - {"alembic_version"}


def audit_function_exists(engine: Engine) -> bool:
    with engine.connect() as connection:
        return bool(
            connection.scalar(
                text("SELECT count(*) FROM pg_proc WHERE proname = 'audit_logs_ajout_seul'")
            )
        )


def test_upgrade_creates_every_model_table(empty_database):
    config, engine = empty_database

    command.upgrade(config, "head")

    assert user_tables(engine) == set(Base.metadata.tables)
    assert len(user_tables(engine)) == 29
    assert audit_function_exists(engine)


def test_downgrade_removes_everything(empty_database):
    config, engine = empty_database
    command.upgrade(config, "head")

    command.downgrade(config, "base")

    assert user_tables(engine) == set()
    assert not audit_function_exists(engine)


def test_upgrade_works_again_after_downgrade(empty_database):
    config, engine = empty_database
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    command.upgrade(config, "head")

    assert len(user_tables(engine)) == 29


def test_migration_0005_fills_only_empty_pointages(empty_database):
    """Données importées avant la règle automatique : seul un pointage vide est rempli."""
    config, engine = empty_database
    command.upgrade(config, "0004")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO companies (id, code, nom) OVERRIDING SYSTEM VALUE VALUES (1, 'C', 'Société');
                INSERT INTO banks (id, code, nom) OVERRIDING SYSTEM VALUE VALUES (1, 'B', 'Banque');
                INSERT INTO currencies (code, libelle) VALUES ('MAD', 'Dirham');
                INSERT INTO bank_accounts (id, company_id, bank_id, libelle, numero, devise)
                    OVERRIDING SYSTEM VALUE VALUES (1, 1, 1, 'Compte', 'N1', 'MAD');
                INSERT INTO bank_statements (id, bank_account_id) OVERRIDING SYSTEM VALUE VALUES (1, 1);
                INSERT INTO pointage_types (id, code, libelle) OVERRIDING SYSTEM VALUE VALUES
                    (1, 'ENCAISSEMENT', 'Encaissement'),
                    (2, 'DECAISSEMENT', 'Décaissement'),
                    (3, 'FRAIS_BANCAIRES', 'Frais bancaires');
                INSERT INTO bank_transactions
                    (statement_id, bank_account_id, date_operation, libelle, debit, credit, montant,
                     hash_ligne, pointage_type_id)
                VALUES
                    (1, 1, '2026-09-02', 'VIR CLIENT ATLAS', 0, 100, 100, 'h1', NULL),
                    (1, 1, '2026-09-03', 'VIR FOURNISSEUR', 50, 0, -50, 'h2', NULL),
                    (1, 1, '2026-09-04', 'AGIOS / FRAIS BANCAIRES', 5, 0, -5, 'h3', NULL),
                    (1, 1, '2026-09-05', 'FRAIS TENUE DE COMPTE', 3, 0, -3, 'h4', NULL),
                    (1, 1, '2026-09-06', 'FRAISIER SA', 0, 7, 7, 'h5', NULL),
                    (1, 1, '2026-09-07', 'COMMISSION', 2, 0, -2, 'h6', 1);
                """
            )
        )

    command.upgrade(config, "head")

    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT hash_ligne, pointage_type_id FROM bank_transactions ORDER BY hash_ligne")
        ).all()
        audit = connection.execute(
            text("SELECT nouvelle_valeur FROM audit_logs WHERE action = 'remplissage_pointage'")
        ).scalar_one()
    assert dict(rows) == {
        "h1": 1,  # crédit → Encaissement
        "h2": 2,  # débit → Décaissement
        "h3": 3,  # AGIOS / FRAIS → Frais bancaires
        "h4": 3,
        "h5": 1,  # « FRAISIER » n'est pas le mot FRAIS
        "h6": 1,  # déjà renseigné : jamais modifié
    }
    assert audit == {"migration": "0005", "operations": 5}


def test_migration_0007_puts_day_amounts_on_line_1(empty_database):
    """Avant 0007, Encaissement / Escompte / Douane valaient pour toute la journée : ils sont
    placés sur la ligne 1, sans perte."""
    config, engine = empty_database
    command.upgrade(config, "0006")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO companies (id, code, nom) OVERRIDING SYSTEM VALUE VALUES (1, 'C', 'Société');
                INSERT INTO saisies_previsions_jour (company_id, jour, encaissement, douane)
                    VALUES (1, '2026-09-30', 250000, -12000.50);
                """
            )
        )

    command.upgrade(config, "head")

    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT ligne, encaissement, escompte, douane FROM saisies_previsions_jour")
        ).all()
    assert [tuple(row) for row in rows] == [(1, Decimal("250000.00"), None, Decimal("-12000.50"))]


def test_migration_0007_downgrade_refuses_to_lose_line_amounts(empty_database):
    config, engine = empty_database
    command.upgrade(config, "head")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO companies (id, code, nom) OVERRIDING SYSTEM VALUE VALUES (1, 'C', 'Société');
                INSERT INTO saisies_previsions_jour (company_id, jour, ligne, escompte)
                    VALUES (1, '2026-09-30', 2, 10);
                """
            )
        )

    with pytest.raises(Exception, match="ligne 1"):
        command.downgrade(config, "0006")


def test_migration_0008_fixes_debits_proven_by_the_balance(empty_database):
    """Relevé BP « Format_Different » importé avec une colonne Montant sans signe : tout était au
    crédit. Seules les opérations dont la chaîne des soldes prouve un débit sont corrigées."""
    config, engine = empty_database
    command.upgrade(config, "0007")

    def h(libelle, debit, credit, solde, jour):
        return line_hash(1, (jour, None, libelle, D(debit), D(credit), D(solde), None), 1)

    rows = [
        # (id, jour, libellé, crédit importé, solde, pointage)
        (1, date(2026, 9, 2), "VIR RECU ALPHA MODE", "38500.00", "223500.00", 1),
        (2, date(2026, 9, 3), "PRLV FOURNISSEUR TEXTILE", "12800.00", "210700.00", 1),
        (3, date(2026, 9, 5), "COMMISSION BANCAIRE", "175.00", "210525.00", 3),
        (4, date(2026, 9, 6), "VIR INCONNU", "999.00", "1.00", 1),  # rien ne prouve un débit
    ]
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO companies (id, code, nom) OVERRIDING SYSTEM VALUE VALUES (1, 'C', 'Société');
                INSERT INTO banks (id, code, nom) OVERRIDING SYSTEM VALUE VALUES (1, 'B', 'Banque');
                INSERT INTO currencies (code, libelle) VALUES ('MAD', 'Dirham');
                INSERT INTO bank_accounts (id, company_id, bank_id, libelle, numero, devise)
                    OVERRIDING SYSTEM VALUE VALUES (1, 1, 1, 'Compte', 'N1', 'MAD');
                INSERT INTO bank_statements (id, bank_account_id, solde_ouverture, solde_cloture)
                    OVERRIDING SYSTEM VALUE VALUES (1, 1, 185000, 210525);
                INSERT INTO pointage_types (id, code, libelle) OVERRIDING SYSTEM VALUE VALUES
                    (1, 'ENCAISSEMENT', 'Encaissement'),
                    (2, 'DECAISSEMENT', 'Décaissement'),
                    (3, 'FRAIS_BANCAIRES', 'Frais bancaires');
                INSERT INTO balance_checks (bank_account_id, bank_statement_id, date_controle,
                    solde_releve, solde_enregistre, ecart, statut, commentaire)
                    VALUES (1, 1, '2026-09-05', 210525, 638000, -427475, 'À vérifier',
                            'Les mouvements du relevé ne retrouvent pas son solde de clôture.');
                """
            )
        )
        for id_, jour, libelle, credit, solde, pointage in rows:
            connection.execute(
                text(
                    """
                    INSERT INTO bank_transactions (id, statement_id, bank_account_id,
                        date_operation, libelle, debit, credit, montant, solde, hash_ligne,
                        pointage_type_id)
                    OVERRIDING SYSTEM VALUE VALUES (:id, 1, 1, :jour, :libelle, 0, :credit,
                        :credit, :solde, :hash, :pointage)
                    """
                ),
                {
                    "id": id_,
                    "jour": jour,
                    "libelle": libelle,
                    "credit": D(credit),
                    "solde": D(solde),
                    "hash": h(libelle, "0.00", credit, solde, jour),
                    "pointage": pointage,
                },
            )

    command.upgrade(config, "head")

    with engine.connect() as connection:
        result = connection.execute(
            text(
                "SELECT id, debit, credit, montant, pointage_type_id, hash_ligne "
                "FROM bank_transactions ORDER BY id"
            )
        ).all()
        check = connection.execute(text("SELECT statut, commentaire FROM balance_checks")).one()
        audit = connection.execute(
            text("SELECT nouvelle_valeur FROM audit_logs WHERE action = 'correction_sens'")
        ).scalar_one()
    by_id = {row.id: row for row in result}
    assert (by_id[1].debit, by_id[1].credit, by_id[1].pointage_type_id) == (
        D("0.00"),
        D("38500.00"),
        1,
    )
    assert (by_id[2].debit, by_id[2].credit, by_id[2].montant, by_id[2].pointage_type_id) == (
        D("12800.00"),
        D("0.00"),
        D("-12800.00"),
        2,  # Encaissement → Décaissement
    )
    assert (by_id[3].debit, by_id[3].pointage_type_id) == (D("175.00"), 3)  # frais : inchangé
    assert (by_id[4].debit, by_id[4].credit) == (D("0.00"), D("999.00"))  # pas de preuve
    # Empreinte recalculée : un nouvel import du fichier reconnaît la ligne comme déjà importée
    assert by_id[2].hash_ligne == h(
        "PRLV FOURNISSEUR TEXTILE", "12800.00", "0.00", "210700.00", date(2026, 9, 3)
    )
    assert by_id[4].hash_ligne == h("VIR INCONNU", "0.00", "999.00", "1.00", date(2026, 9, 6))
    # La ligne 4 garde le relevé incohérent : le contrôle reste « À vérifier »
    assert check.statut == "À vérifier"
    assert audit == {"migration": "0008", "operations": [2, 3], "releves": [1]}


def test_migration_0008_turns_a_coherent_statement_check_into_an_ecart(empty_database):
    config, engine = empty_database
    command.upgrade(config, "0007")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO companies (id, code, nom) OVERRIDING SYSTEM VALUE VALUES (1, 'C', 'Société');
                INSERT INTO banks (id, code, nom) OVERRIDING SYSTEM VALUE VALUES (1, 'B', 'Banque');
                INSERT INTO currencies (code, libelle) VALUES ('MAD', 'Dirham');
                INSERT INTO bank_accounts (id, company_id, bank_id, libelle, numero, devise)
                    OVERRIDING SYSTEM VALUE VALUES (1, 1, 1, 'Compte', 'N1', 'MAD');
                INSERT INTO bank_statements (id, bank_account_id, solde_ouverture, solde_cloture)
                    OVERRIDING SYSTEM VALUE VALUES (1, 1, 1000, 900);
                INSERT INTO bank_transactions (statement_id, bank_account_id, date_operation,
                    libelle, debit, credit, montant, solde, hash_ligne)
                    VALUES (1, 1, '2026-09-02', 'PRLV', 0, 100, 100, 900, 'h1');
                INSERT INTO balance_checks (bank_account_id, bank_statement_id, date_controle,
                    solde_releve, solde_enregistre, ecart, statut, commentaire)
                    VALUES (1, 1, '2026-09-02', 900, 1000, -100, 'À vérifier', 'incohérent'),
                           (1, 1, '2026-09-02', 900, 900, 0, 'À vérifier', 'incohérent');
                """
            )
        )

    command.upgrade(config, "head")

    with engine.connect() as connection:
        checks = connection.execute(
            text("SELECT statut, commentaire FROM balance_checks ORDER BY id")
        ).all()
    # 1 000 − 100 = 900 : les mouvements retrouvent le solde de clôture
    assert [tuple(row) for row in checks] == [("Écart", None), ("Conforme", None)]


@pytest.mark.parametrize(
    ("before", "after", "audited"),
    [
        ("Société X", "Tefil", True),
        ("Nom choisi par un utilisateur", "Nom choisi par un utilisateur", False),
    ],
)
def test_migration_0009_names_the_second_company_tefil(empty_database, before, after, audited):
    """Nom confirmé le 05/10/2026 ; un nom déjà changé par un utilisateur n'est jamais écrasé."""
    config, engine = empty_database
    command.upgrade(config, "0008")
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO companies (code, nom) VALUES ('SOCX', :nom)"), {"nom": before}
        )

    command.upgrade(config, "head")

    with engine.connect() as connection:
        nom = connection.execute(text("SELECT nom FROM companies WHERE code = 'SOCX'")).scalar()
        audit = connection.execute(
            text(
                "SELECT ancienne_valeur, nouvelle_valeur FROM audit_logs WHERE action = 'renommage_societe'"
            )
        ).all()
    assert nom == after
    assert [tuple(row) for row in audit] == (
        [({"nom": "Société X"}, {"nom": "Tefil"})] if audited else []
    )


def test_migration_matches_models(empty_database):
    """Échoue si un modèle a changé sans migration (colonne, contrainte ou index oublié)."""
    config, _ = empty_database
    command.upgrade(config, "head")

    command.check(config)  # lève AutogenerateDiffsDetected en cas de différence
