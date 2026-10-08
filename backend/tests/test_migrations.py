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

    command.upgrade(config, "0005")  # la migration 0017 re-pointe ensuite

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

    command.upgrade(config, "0008")  # la migration 0017 re-pointe ensuite

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
        columns = {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'bank_accounts'"
                )
            )
        }
    assert "journal_sage" not in columns


def test_migration_0013_takes_past_decisions_from_validation_and_audit(empty_database):
    """Les décisions passées gardent leur auteur et leur date : la validation depuis la
    correspondance, le rejet et l'annulation depuis la dernière trace d'audit."""
    config, engine = empty_database
    command.upgrade(config, "0012")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO companies (id, code, nom) OVERRIDING SYSTEM VALUE VALUES (1, 'C', 'Société');
                INSERT INTO users (id, nom, email, mot_de_passe_hash) OVERRIDING SYSTEM VALUE VALUES
                    (1, 'Mustapha', 'm@example.com', 'x'), (2, 'Salma', 's@example.com', 'x');
                INSERT INTO reconciliation_matches
                    (id, company_id, type, origine, statut, valide_par_id, valide_le)
                    OVERRIDING SYSTEM VALUE
                VALUES
                    (1, 1, '1-1', 'Automatique', 'Validée', 1, '2026-10-01 09:00+00'),
                    (2, 1, '1-1', 'Automatique', 'Rejetée', NULL, NULL),
                    (3, 1, '1-1', 'Automatique', 'Annulée', 1, '2026-10-01 10:00+00'),
                    (4, 1, '1-1', 'Automatique', 'Proposée', NULL, NULL);
                INSERT INTO audit_logs (user_id, action, entite, entite_id, created_at) VALUES
                    (2, 'rejet_rapprochement', 'reconciliation_match', '2', '2026-10-02 08:00+00'),
                    (1, 'validation_rapprochement', 'reconciliation_match', '3', '2026-10-01 10:00+00'),
                    (2, 'annulation_rapprochement', 'reconciliation_match', '3', '2026-10-03 11:00+00');
                """
            )
        )

    command.upgrade(config, "0013")

    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT id, decide_par_id, to_char(decide_le AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI') "
                "FROM reconciliation_matches ORDER BY id"
            )
        ).all()
    assert [tuple(row) for row in rows] == [
        (1, 1, "2026-10-01 09:00"),
        (2, 2, "2026-10-02 08:00"),
        (3, 2, "2026-10-03 11:00"),
        (4, None, None),
    ]


def test_migration_0014_scores_on_amount_date_and_label(empty_database):
    """Décision du 07/10/2026 : montant 50, date 30, libellé 20 ; référence et tiers désactivés."""
    config, engine = empty_database
    command.upgrade(config, "0013")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO reconciliation_rules (code, libelle, critere, poids, tolerance) VALUES
                    ('REFERENCE', 'Référence', 'reference', 40, NULL),
                    ('MONTANT', 'Montant', 'montant', 30, NULL),
                    ('DATE', 'Date', 'date', 15, 3),
                    ('LIBELLE', 'Libellé', 'libelle', 10, NULL),
                    ('TIERS', 'Tiers', 'tiers', 5, NULL),
                    ('SEUIL_FORT', 'Seuil', 'seuil', 90, NULL);
                """
            )
        )

    def grid() -> dict[str, tuple[int, bool]]:
        with engine.connect() as connection:
            rows = connection.execute(text("SELECT code, poids, actif FROM reconciliation_rules"))
            return {row[0]: (int(row[1]), row[2]) for row in rows}

    command.upgrade(config, "0014")
    after = grid()
    command.downgrade(config, "0013")

    assert after == {
        "REFERENCE": (40, False),
        "MONTANT": (50, True),
        "DATE": (30, True),
        "LIBELLE": (20, True),
        "TIERS": (5, False),
        "SEUIL_FORT": (90, True),
    }
    assert grid() == {
        "REFERENCE": (40, True),
        "MONTANT": (30, True),
        "DATE": (15, True),
        "LIBELLE": (10, True),
        "TIERS": (5, True),
        "SEUIL_FORT": (90, True),
    }


_DONNEES_0015 = """
INSERT INTO companies (id, code, nom) OVERRIDING SYSTEM VALUE VALUES (1, 'C', 'Société');
INSERT INTO banks (id, code, nom) OVERRIDING SYSTEM VALUE VALUES (1, 'B', 'Banque');
INSERT INTO currencies (code, libelle) VALUES ('MAD', 'Dirham');
INSERT INTO bank_accounts (id, company_id, bank_id, libelle, numero, devise)
    OVERRIDING SYSTEM VALUE VALUES (1, 1, 1, 'Compte', 'N1', 'MAD');
INSERT INTO bank_statements (id, bank_account_id) OVERRIDING SYSTEM VALUE VALUES (1, 1);
INSERT INTO bank_transactions (id, statement_id, bank_account_id, date_operation, libelle,
    debit, credit, montant, hash_ligne, statut) OVERRIDING SYSTEM VALUE VALUES
    (1, 1, 1, '2026-09-30', 'COMMISSION', 20, 0, -20, 'h1', 'Écart'),
    (2, 1, 1, '2026-09-30', 'VIR CLIENT', 0, 100, 100, 'h2', 'Non rapprochée');
INSERT INTO accounting_entries (id, company_id, bank_account_id, date_ecriture, libelle,
    debit, credit, montant, hash_ligne, statut) OVERRIDING SYSTEM VALUE VALUES
    (1, 1, 1, '2026-09-28', 'CHEQUE', 0, 500, 500, 'e1', 'Écart');
INSERT INTO users (id, nom, email, mot_de_passe_hash) OVERRIDING SYSTEM VALUE VALUES
    (1, 'Admin', 'admin@example.com', 'x'), (2, 'Comptable', 'c@example.com', 'x');
INSERT INTO discrepancies (id, company_id, type, bank_transaction_id, accounting_entry_id,
    montant, date_ecart, statut, commentaire, cloture_le, cloture_par_id)
    OVERRIDING SYSTEM VALUE VALUES
    (1, 1, 'Banque sans écriture', 1, NULL, 20, '2026-09-30', 'À traiter', NULL, NULL, NULL),
    (2, 1, 'Écriture sans banque', NULL, 1, 500, '2026-09-28', 'Traité', 'Relancé', NULL, NULL),
    (3, 1, 'Banque sans écriture', 2, NULL, 100, '2026-09-30', 'Clôturé', 'Réglé',
        '2026-10-01 09:00+00', 2);
"""


def _add_admin(connection) -> None:
    connection.execute(
        text(
            """
            INSERT INTO roles (id, code, nom) OVERRIDING SYSTEM VALUE VALUES (1, 'ADMIN', 'Admin');
            INSERT INTO user_roles (user_id, role_id) VALUES (1, 1);
            """
        )
    )


def test_migration_0015_closes_open_discrepancies_and_frees_their_lines(empty_database):
    """Décision du 07/10/2026 : la fonction Écarts est mise de côté ; les écarts ouverts sont
    clôturés comme à l'écran et leurs lignes redeviennent « Non rapprochée »."""
    config, engine = empty_database
    command.upgrade(config, "0014")
    with engine.begin() as connection:
        connection.execute(text(_DONNEES_0015))
        _add_admin(connection)

    command.upgrade(config, "0015")

    with engine.connect() as connection:
        ecarts = connection.execute(
            text(
                "SELECT id, statut, commentaire, cloture_par_id, cloture_le IS NOT NULL "
                "FROM discrepancies ORDER BY id"
            )
        ).all()
        lignes = connection.execute(
            text(
                "SELECT 'tx', id, statut FROM bank_transactions "
                "UNION ALL SELECT 'ec', id, statut FROM accounting_entries ORDER BY 1, 2"
            )
        ).all()
        audit = connection.execute(
            text(
                "SELECT entite_id, user_id, ancienne_valeur ->> 'statut' FROM audit_logs "
                "WHERE action = 'cloture_ecart' ORDER BY entite_id"
            )
        ).all()
    motif = "Fonction Écarts mise de côté le 07/10/2026."
    assert [tuple(row) for row in ecarts] == [
        (1, "Clôturé", motif, 1, True),
        (2, "Clôturé", f"Relancé {motif}", 1, True),
        (3, "Clôturé", "Réglé", 2, True),  # déjà clôturé : intact
    ]
    assert [tuple(row) for row in lignes] == [
        ("ec", 1, "Non rapprochée"),
        ("tx", 1, "Non rapprochée"),
        ("tx", 2, "Non rapprochée"),
    ]
    assert [tuple(row) for row in audit] == [("1", 1, "À traiter"), ("2", 1, "Traité")]


def test_migration_0015_needs_an_administrator_to_close(empty_database):
    config, engine = empty_database
    command.upgrade(config, "0014")
    with engine.begin() as connection:
        connection.execute(text(_DONNEES_0015))

    with pytest.raises(Exception, match="aucun administrateur actif"):
        command.upgrade(config, "0015")


def test_migration_0016_deletes_inactive_accounts_without_history(empty_database):
    """Décision du 08/10/2026 : un compte désactivé sans historique est effacé avec ses soldes
    saisis ; un compte actif, ou désactivé avec un historique, reste."""
    config, engine = empty_database
    command.upgrade(config, "0015")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO companies (id, code, nom) OVERRIDING SYSTEM VALUE VALUES (1, 'C', 'S');
                INSERT INTO banks (id, code, nom) OVERRIDING SYSTEM VALUE VALUES (1, 'B', 'Banque');
                INSERT INTO currencies (code, libelle) VALUES ('MAD', 'Dirham');
                INSERT INTO bank_accounts (id, company_id, bank_id, libelle, numero, devise, actif)
                    OVERRIDING SYSTEM VALUE VALUES
                    (1, 1, 1, 'Actif', 'N1', 'MAD', true),
                    (2, 1, 1, 'Désactivé sans historique', 'N2', 'MAD', false),
                    (3, 1, 1, 'Désactivé avec relevé', 'N3', 'MAD', false);
                INSERT INTO bank_account_balances (bank_account_id, date_solde, solde, source)
                    VALUES (1, '2026-10-01', 10, 'Saisie'), (2, '2026-10-01', 20, 'Saisie');
                INSERT INTO bank_statements (bank_account_id) VALUES (3);
                """
            )
        )

    command.upgrade(config, "0016")

    with engine.connect() as connection:
        comptes = connection.execute(text("SELECT id FROM bank_accounts ORDER BY id")).scalars()
        soldes = connection.execute(
            text("SELECT bank_account_id FROM bank_account_balances ORDER BY 1")
        ).scalars()
        audit = connection.execute(
            text(
                "SELECT entite_id, ancienne_valeur ->> 'soldes_saisis_effaces' FROM audit_logs "
                "WHERE action = 'suppression_compte'"
            )
        ).all()
        assert list(comptes) == [1, 3]
        assert list(soldes) == [1]
    assert [tuple(row) for row in audit] == [("2", "1")]


def test_migration_0017_creates_the_74_categories_and_repoints(empty_database):
    """Décision du 08/10/2026 : les 74 catégories remplacent les trois anciens types ; les opérations
    sont re-pointées par les mots-clés, sinon vides, avec une trace d'audit chacune."""
    config, engine = empty_database
    command.upgrade(config, "0016")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO companies (id, code, nom) OVERRIDING SYSTEM VALUE VALUES (1, 'C', 'S');
                INSERT INTO banks (id, code, nom) OVERRIDING SYSTEM VALUE VALUES (1, 'B', 'Banque');
                INSERT INTO currencies (code, libelle) VALUES ('MAD', 'Dirham');
                INSERT INTO bank_accounts (id, company_id, bank_id, libelle, numero, devise)
                    OVERRIDING SYSTEM VALUE VALUES (1, 1, 1, 'Compte', 'N1', 'MAD');
                INSERT INTO bank_statements (id, bank_account_id) OVERRIDING SYSTEM VALUE
                    VALUES (1, 1);
                INSERT INTO pointage_types (id, code, libelle) OVERRIDING SYSTEM VALUE VALUES
                    (1, 'ENCAISSEMENT', 'Encaissement'),
                    (2, 'DECAISSEMENT', 'Décaissement'),
                    (3, 'FRAIS_BANCAIRES', 'Frais bancaires');
                INSERT INTO bank_transactions (id, statement_id, bank_account_id, date_operation,
                    libelle, debit, credit, montant, hash_ligne, pointage_type_id)
                    OVERRIDING SYSTEM VALUE VALUES
                    (1, 1, 1, '2026-09-01', 'COMMISSION BANCAIRE', 5, 0, -5, 'h1', 3),
                    (2, 1, 1, '2026-09-02', 'VIR CLIENT ATLAS', 0, 100, 100, 'h2', 1),
                    (3, 1, 1, '2026-09-03', 'AGIOS D''ECHELLE T3', 9, 0, -9, 'h3', 3),
                    (4, 1, 1, '2026-09-04', 'A VOIR AVEC LA BANQUE', 7, 0, -7, 'h4', 2);
                """
            )
        )

    command.upgrade(config, "0017")

    with engine.connect() as connection:
        actifs = connection.execute(
            text("SELECT count(*) FROM pointage_types WHERE actif")
        ).scalar_one()
        anciens = connection.execute(
            text("SELECT code FROM pointage_types WHERE NOT actif ORDER BY code")
        ).scalars()
        pointes = connection.execute(
            text(
                "SELECT t.id, p.libelle FROM bank_transactions t "
                "LEFT JOIN pointage_types p ON p.id = t.pointage_type_id ORDER BY t.id"
            )
        ).all()
        audit = connection.execute(
            text(
                "SELECT entite_id, ancienne_valeur ->> 'pointage', nouvelle_valeur ->> 'pointage' "
                "FROM audit_logs WHERE action = 'repointage' ORDER BY entite_id"
            )
        ).all()
        longueur = connection.execute(
            text(
                "SELECT character_maximum_length FROM information_schema.columns "
                "WHERE table_name = 'pointage_types' AND column_name = 'code'"
            )
        ).scalar_one()
        assert actifs == 74
        assert list(anciens) == ["DECAISSEMENT", "ENCAISSEMENT", "FRAIS_BANCAIRES"]
    assert [tuple(row) for row in pointes] == [
        (1, "COM"),  # synonyme COMMISSION
        (2, None),  # rien de reconnu : à choisir
        (3, "AGIOS D'ECHELLE"),  # le plus long nom gagne
        (4, None),  # « A voir » n'est jamais automatique
    ]
    assert [tuple(row) for row in audit] == [
        ("1", "Frais bancaires", "COM"),
        ("2", "Encaissement", None),
        ("3", "Frais bancaires", "AGIOS D'ECHELLE"),
        ("4", "Décaissement", None),
    ]
    assert longueur == 60


def test_migration_matches_models(empty_database):
    """Échoue si un modèle a changé sans migration (colonne, contrainte ou index oublié)."""
    config, _ = empty_database
    command.upgrade(config, "head")

    command.check(config)  # lève AutogenerateDiffsDetected en cas de différence


def test_migration_0019_strong_threshold_is_80(empty_database):
    """Décision du 08/10/2026 : forte correspondance à partir de 80 ; l'écart ne fait que signaler."""
    config, engine = empty_database
    command.upgrade(config, "0018")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO reconciliation_rules (code, libelle, critere, poids, tolerance) VALUES
                    ('SEUIL_FORT', 'Score d''une forte correspondance', 'seuil', 90, NULL),
                    ('ECART_AMBIGUITE', 'Ancien', 'seuil', 10, NULL);
                """
            )
        )

    def grid() -> dict[str, tuple[int, str]]:
        with engine.connect() as connection:
            rows = connection.execute(text("SELECT code, poids, libelle FROM reconciliation_rules"))
            return {row[0]: (int(row[1]), row[2]) for row in rows}

    command.upgrade(config, "0019")
    after = grid()
    command.downgrade(config, "0018")
    before = grid()

    assert after["SEUIL_FORT"][0] == 80
    assert after["ECART_AMBIGUITE"] == (
        10,
        "Écart de points sous lequel une 2e écriture est signalée comme proche",
    )
    assert before["SEUIL_FORT"][0] == 90
