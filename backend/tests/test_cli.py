"""Commande de gestion des comptes : `python -m app.cli`."""

from contextlib import nullcontext
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app import cli
from app.core.security import verify_password
from app.models import AuditLog, BankAccountBalance, BankTransaction, User, UserSession
from tests.helpers import build_transaction, login, make_auth_user, make_world, save


@pytest.fixture
def run(db, monkeypatch, capsys):
    """Lance la commande sur la base de test et retourne (code de sortie, sortie, erreurs)."""
    monkeypatch.setattr(cli, "SessionLocal", lambda: nullcontext(db))

    def _run(*args: str) -> tuple[int, str, str]:
        code = cli.main(list(args))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return _run


def printed_password(output: str) -> str:
    line = next(line for line in output.splitlines() if line.startswith("Mot de passe : "))
    return line.removeprefix("Mot de passe : ")


def test_create_user_prints_a_password_that_works(run, reference):
    code, out, _ = run(
        "create-user", "--email", "Admin@Simtis.ma", "--nom", "Administrateur", "--role", "ADMIN"
    )

    assert code == 0
    user = reference.scalar(select(User).filter_by(email="admin@simtis.ma"))
    password = printed_password(out)
    assert len(password) >= 12
    assert verify_password(password, user.mot_de_passe_hash)
    assert password not in user.mot_de_passe_hash
    assert [role.code for role in user.roles] == ["ADMIN"]
    assert "ne sera plus jamais affiché" in out


def test_create_user_with_several_roles(run, reference):
    code, _, _ = run(
        "create-user",
        "--email",
        "m@simtis.ma",
        "--nom",
        "M",
        "--role",
        "COMPTABLE",
        "--role",
        "RESPONSABLE",
    )

    assert code == 0
    user = reference.scalar(select(User).filter_by(email="m@simtis.ma"))
    assert sorted(role.code for role in user.roles) == ["COMPTABLE", "RESPONSABLE"]


def test_create_user_is_audited_without_the_password(run, reference):
    _, out, _ = run("create-user", "--email", "a@simtis.ma", "--nom", "A", "--role", "ADMIN")

    entry = reference.scalar(select(AuditLog).filter_by(action="creation_utilisateur"))
    assert entry.nouvelle_valeur == {"email": "a@simtis.ma", "nom": "A", "roles": ["ADMIN"]}
    assert printed_password(out) not in str(entry.nouvelle_valeur)


def test_duplicate_email_is_refused(run, reference):
    run("create-user", "--email", "a@simtis.ma", "--nom", "A", "--role", "ADMIN")

    code, _, err = run("create-user", "--email", "A@simtis.ma", "--nom", "B", "--role", "ADMIN")

    assert code == 1
    assert "existe déjà" in err


def test_unknown_role_is_refused(run, reference):
    code, _, err = run("create-user", "--email", "a@simtis.ma", "--nom", "A", "--role", "PATRON")

    assert code == 1
    assert "PATRON" in err
    assert reference.scalar(select(User).filter_by(email="a@simtis.ma")) is None


def test_set_password_unlocks_and_closes_open_sessions(run, client, reference, db):
    user = make_auth_user(reference, "TRESORERIE", email="salma@example.com")
    login(client, "salma@example.com")
    user.echecs_connexion = 3
    db.flush()

    code, out, _ = run("set-password", "--email", "salma@example.com")

    assert code == 0
    db.refresh(user)
    assert verify_password(printed_password(out), user.mot_de_passe_hash)
    assert user.echecs_connexion == 0
    sessions = db.scalars(select(UserSession).filter_by(user_id=user.id)).all()
    assert sessions and all(session.revoked_at is not None for session in sessions)
    assert client.post("/api/auth/refresh").status_code == 401
    assert db.scalar(select(AuditLog).filter_by(action="modification_mot_de_passe")) is not None


def test_set_password_for_unknown_email_is_refused(run, reference):
    code, _, err = run("set-password", "--email", "personne@example.com")

    assert code == 1
    assert "Aucun compte" in err


# --- Recalcul des soldes d'un relevé importé sans soldes (08/10/2026) ------------------------------


def _statement_without_balances(db):
    world = make_world(db)
    for jour, montant in ((2, "1000"), (3, "-250"), (3, "50")):
        value = Decimal(montant)
        save(
            db,
            build_transaction(
                world.statement,
                date_operation=date(2026, 9, jour),
                debit=max(-value, Decimal(0)),
                credit=max(value, Decimal(0)),
                montant=value,
            ),
        )
    return world


def test_recompute_balances_of_an_imported_statement(run, db):
    world = _statement_without_balances(db)

    code, out, _ = run(
        "recalculer-soldes", "--releve", str(world.statement.id), "--solde-ouverture", "5000000"
    )

    assert code == 0, out
    assert "3 soldes calculés" in out
    rows = db.scalars(
        select(BankTransaction)
        .filter_by(statement_id=world.statement.id)
        .order_by(BankTransaction.date_operation, BankTransaction.id)
    ).all()
    assert [(row.solde, row.solde_calcule) for row in rows] == [
        (Decimal("5001000.00"), True),
        (Decimal("5000750.00"), True),
        (Decimal("5000800.00"), True),
    ]
    db.refresh(world.statement)
    assert (world.statement.solde_ouverture, world.statement.solde_cloture) == (
        Decimal("5000000.00"),
        Decimal("5000800.00"),
    )
    balance = db.scalar(select(BankAccountBalance).filter_by(bank_account_id=world.account.id))
    assert (balance.date_solde.isoformat(), balance.solde, balance.source) == (
        "2026-09-03",
        Decimal("5000800.00"),
        "Relevé",
    )
    [log] = db.scalars(select(AuditLog).filter_by(action="recalcul_soldes")).all()
    assert log.nouvelle_valeur["operations"] == 3


def test_recompute_refuses_a_statement_with_file_balances_or_a_bad_amount(run, db):
    world = _statement_without_balances(db)
    first = db.scalars(select(BankTransaction).filter_by(statement_id=world.statement.id)).first()
    first.solde = Decimal("10")
    db.flush()

    refused = run(
        "recalculer-soldes", "--releve", str(world.statement.id), "--solde-ouverture", "0"
    )
    bad = run("recalculer-soldes", "--releve", str(world.statement.id), "--solde-ouverture", "x")
    missing = run("recalculer-soldes", "--releve", "999999", "--solde-ouverture", "0")

    assert refused[0] == 1 and "déjà ses soldes" in refused[2]
    assert bad[0] == 1 and "illisible" in bad[2]
    assert missing[0] == 1 and "introuvable" in missing[2]
