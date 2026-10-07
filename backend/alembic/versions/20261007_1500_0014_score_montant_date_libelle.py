"""score montant date libelle

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-07 15:00:00

Données seulement. Décision du 07/10/2026 : pour le moment, le score du rapprochement ne repose que
sur le montant (50), la date (30) et le libellé (20). La référence et le tiers sont désactivés : leurs
lignes restent (avec leurs anciens points) pour pouvoir les réactiver. Les seuils ne changent pas.
Les propositions en attente gardent leur score jusqu'au prochain lancement du moteur.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOUVELLE = {"MONTANT": 50, "DATE": 30, "LIBELLE": 20}
ANCIENNE = {"MONTANT": 30, "DATE": 15, "LIBELLE": 10}


def _set(points: dict[str, int], actif_reference_tiers: bool) -> None:
    for code, valeur in points.items():
        op.execute(
            f"UPDATE reconciliation_rules SET poids = {valeur}, updated_at = now() "
            f"WHERE code = '{code}'"
        )
    op.execute(
        f"UPDATE reconciliation_rules SET actif = {str(actif_reference_tiers).lower()}, "
        "updated_at = now() WHERE code IN ('REFERENCE', 'TIERS')"
    )


def upgrade() -> None:
    # Une base sans grille (encore jamais seedée) n'est pas touchée : les seeds la créeront
    _set(NOUVELLE, actif_reference_tiers=False)


def downgrade() -> None:
    _set(ANCIENNE, actif_reference_tiers=True)
