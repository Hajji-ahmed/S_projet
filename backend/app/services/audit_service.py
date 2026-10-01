"""Journal des actions sensibles (CDC §11).

`log()` ajoute la ligne dans la transaction en cours, sans la valider : l'action et sa trace sont
enregistrées ensemble, ou pas du tout. Les valeurs avant / après sont converties en JSON sans perte
(un montant `Decimal` devient un texte exact, jamais un nombre à virgule flottante).
"""

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog
from app.repositories import audit_repository

MASK = "[masqué]"

# Champs dont la valeur n'est jamais écrite dans le journal, quelle que soit l'action
SENSITIVE_KEYS = frozenset(
    {
        "password",
        "mot_de_passe",
        "mot_de_passe_hash",
        "token",
        "token_hash",
        "access_token",
        "session_token",
        "refresh_token",
        "jwt_secret",
    }
)


def to_json(value: Any) -> Any:
    """Convertit une valeur en JSON exact et masque les champs sensibles, à toute profondeur."""
    if isinstance(value, Mapping):
        return {
            str(key): MASK if str(key).lower() in SENSITIVE_KEYS else to_json(item)
            for key, item in value.items()
        }
    if isinstance(value, set | frozenset):
        return sorted(to_json(item) for item in value)
    if isinstance(value, list | tuple):
        return [to_json(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Enum):
        return to_json(value.value)
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return str(value)


def log(
    db: Session,
    *,
    user_id: int | None,
    action: str,
    entite: str,
    entite_id: int | str | None = None,
    avant: Mapping[str, Any] | None = None,
    apres: Mapping[str, Any] | None = None,
    ip: str | None = None,
) -> AuditLog:
    """Enregistre une action. `user_id=None` pour une action système (commande en ligne, tentative anonyme)."""
    entry = AuditLog(
        user_id=user_id,
        action=action,
        entite=entite,
        entite_id=None if entite_id is None else str(entite_id),
        ancienne_valeur=None if avant is None else to_json(avant),
        nouvelle_valeur=None if apres is None else to_json(apres),
        ip=ip,
    )
    return audit_repository.add(db, entry)
