"""Erreurs métier levées par les services.

Les services ne connaissent pas HTTP : ils lèvent ces erreurs, et `app/main.py` les convertit en
réponses (404, 409) avec le message tel quel dans `detail`. Le message est destiné à l'utilisateur :
il doit être en français et dire quoi faire.
"""


class DomainError(Exception):
    """Base des erreurs métier. `message` est affiché à l'utilisateur."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    """L'élément demandé n'existe pas (404)."""


class ConflictError(DomainError):
    """L'action contredit l'état actuel des données : doublon, règle métier non respectée (409)."""
