"""Commande de gestion des comptes : `python -m app.cli`."""

from contextlib import nullcontext

import pytest
from sqlalchemy import select

from app import cli
from app.core.security import verify_password
from app.models import AuditLog, User, UserSession
from tests.helpers import login, make_auth_user


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
