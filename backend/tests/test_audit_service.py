"""Le service d'audit : valeurs exactes, champs sensibles masqués, même transaction que l'action."""

from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import select

from app.models import AuditLog
from app.services import audit_service
from app.services.audit_service import MASK, to_json


class Couleur(StrEnum):
    TEAL = "teal"


def test_decimal_is_kept_exactly_as_text():
    assert to_json({"montant": Decimal("1234567890123456.78")}) == {
        "montant": "1234567890123456.78"
    }


def test_dates_are_written_in_iso_format():
    value = {"jour": date(2026, 9, 30), "instant": datetime(2026, 9, 30, 14, 30, tzinfo=UTC)}

    assert to_json(value) == {"jour": "2026-09-30", "instant": "2026-09-30T14:30:00+00:00"}


def test_sets_become_sorted_lists_and_enums_their_value():
    assert to_json({"roles": {"TRESORERIE", "ADMIN"}, "c": Couleur.TEAL}) == {
        "roles": ["ADMIN", "TRESORERIE"],
        "c": "teal",
    }


def test_sensitive_fields_are_masked_at_any_depth():
    value = {
        "email": "salma@example.com",
        "mot_de_passe": "secret-1",
        "Password": "secret-2",
        "details": {"token_hash": "abc", "liste": [{"access_token": "xyz"}]},
    }

    result = to_json(value)

    assert result == {
        "email": "salma@example.com",
        "mot_de_passe": MASK,
        "Password": MASK,
        "details": {"token_hash": MASK, "liste": [{"access_token": MASK}]},
    }
    assert "secret" not in str(result) and "xyz" not in str(result)


def test_log_writes_one_entry_with_before_and_after(db):
    entry = audit_service.log(
        db,
        user_id=3,
        action="modification_prevision",
        entite="cash_forecast",
        entite_id=12,
        avant={"montant": Decimal("100.00"), "date_prevue": date(2026, 10, 1)},
        apres={"montant": Decimal("150.50"), "date_prevue": date(2026, 10, 2)},
        ip="10.0.0.5",
    )

    saved = db.scalar(select(AuditLog).where(AuditLog.id == entry.id))
    assert saved.user_id == 3
    assert saved.entite_id == "12"
    assert saved.ancienne_valeur == {"montant": "100.00", "date_prevue": "2026-10-01"}
    assert saved.nouvelle_valeur == {"montant": "150.50", "date_prevue": "2026-10-02"}
    assert saved.ip == "10.0.0.5"


def test_log_is_part_of_the_caller_transaction(db):
    """Si l'action est annulée, sa trace l'est aussi : jamais de trace d'une action non faite."""
    savepoint = db.begin_nested()
    audit_service.log(db, user_id=None, action="action_annulee", entite="test")
    savepoint.rollback()

    assert db.scalar(select(AuditLog).where(AuditLog.action == "action_annulee")) is None


def test_missing_before_value_is_a_real_sql_null(db):
    """Une création n'a pas de valeur « avant » : NULL SQL, pour que `IS NULL` la trouve."""
    entry = audit_service.log(
        db, user_id=None, action="creation_test", entite="test", apres={"a": 1}
    )

    found = db.scalar(
        select(AuditLog).where(AuditLog.id == entry.id, AuditLog.ancienne_valeur.is_(None))
    )

    assert found is not None
