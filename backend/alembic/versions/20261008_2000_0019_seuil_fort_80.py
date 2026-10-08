"""seuil fort 80

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-08 20:00:00

Données seulement. Décision du 08/10/2026 : une forte correspondance commence à 80 (au lieu de 90),
et seule une égalité de score rend une opération ambiguë. `ECART_AMBIGUITE` (10) ne sert plus qu'à
signaler une 2e écriture proche sur la proposition. « Forte » se calcule à la lecture : les
propositions en attente changent tout de suite ; les ambiguës, au prochain lancement du moteur.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LIBELLE_ECART = "Écart de points sous lequel une 2e écriture est signalée comme proche"
ANCIEN_LIBELLE_ECART = "Écart de points sous lequel deux candidats sont ambigus"


def _set(seuil_fort: int, libelle_ecart: str) -> None:
    # Une base sans grille (encore jamais seedée) n'est pas touchée : les seeds la créeront
    op.execute(
        f"UPDATE reconciliation_rules SET poids = {seuil_fort}, updated_at = now() "
        "WHERE code = 'SEUIL_FORT'"
    )
    op.execute(
        f"UPDATE reconciliation_rules SET libelle = '{libelle_ecart}', updated_at = now() "
        "WHERE code = 'ECART_AMBIGUITE'"
    )


def upgrade() -> None:
    _set(80, LIBELLE_ECART)


def downgrade() -> None:
    _set(90, ANCIEN_LIBELLE_ECART)
