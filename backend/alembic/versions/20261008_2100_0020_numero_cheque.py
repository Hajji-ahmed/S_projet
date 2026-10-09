"""numero de cheque

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-08 21:00:00

Données seulement. Décision du 08/10/2026 : les chèques se rapprochent aussi par leur numéro. Le
critère `REFERENCE` est réactivé à 40 points ; il lit maintenant les numéros de 5 chiffres ou plus
des libellés (sans les zéros en tête). Le total reste plafonné à 100. Les propositions en attente
gardent leur score jusqu'au prochain lancement du moteur.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _set(actif: bool, libelle: str) -> None:
    # Une base sans grille (encore jamais seedée) n'est pas touchée : les seeds la créeront
    op.execute(
        f"UPDATE reconciliation_rules SET actif = {str(actif).lower()}, poids = 40, "
        f"libelle = '{libelle}', updated_at = now() WHERE code = 'REFERENCE'"
    )


def upgrade() -> None:
    _set(True, "N° chèque / référence identique")


def downgrade() -> None:
    _set(False, "Référence / n° chèque / n° pièce identique")
