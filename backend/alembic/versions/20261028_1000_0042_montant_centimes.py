"""montant avec ou sans centimes, especes degressives

Revision ID: 0042
Revises: 0041
Create Date: 2026-10-28 10:00:00

Données seulement. Décision du 28/10/2026 : un montant identique vaut 60 points s'il a des
centimes (règle `MONTANT`, 50 avant) et 40 s'il est rond (règle `MONTANT_ROND`, créée par les
seeds au démarrage). Un `MONTANT` changé à la main (autre que 50) est gardé. La règle
`FENETRE_ESPECES` change de sens : les espèces ne sont plus bloquées au-delà de 2 jours, leurs
points de date sont pleins jusque-là puis dégressifs. Les propositions en attente gardent leur
score jusqu'au prochain lancement du moteur.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _montant(avant: int, apres: int, libelle: str) -> None:
    # Une base sans grille (encore jamais seedée) n'est pas touchée : les seeds la créeront
    op.execute(
        f"UPDATE reconciliation_rules SET poids = {apres}, libelle = '{libelle}', "
        f"updated_at = now() WHERE code = 'MONTANT' AND poids = {avant}"
    )


def _especes(libelle: str) -> None:
    op.execute(
        f"UPDATE reconciliation_rules SET libelle = '{libelle}', updated_at = now() "
        "WHERE code = 'FENETRE_ESPECES'"
    )


def upgrade() -> None:
    _montant(50, 60, "Montant identique, avec centimes")
    _especes("Espèces : jours à date pleine autour de l''échéance Sage")


def downgrade() -> None:
    _montant(60, 50, "Montant exact, sens opposé")
    _especes("Espèces : écart maximal avec l''échéance Sage (jours)")
    op.execute("DELETE FROM reconciliation_rules WHERE code = 'MONTANT_ROND'")
