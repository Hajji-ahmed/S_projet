"""barème de date des espèces fixé dans le code

Revision ID: 0043
Revises: 0042
Create Date: 2026-10-30 10:00:00

Décision du 30/10/2026 : la date d'une paire Espèces vaut 30 points à l'échéance exacte, 15 à
1 jour, 10 de 2 à 5 jours, 5 de 6 à 10 jours (`reconciliation_scoring.BAREME_ESPECES`). Le
paramètre « Espèces : jours à date pleine » (FENETRE_ESPECES) n'a plus d'effet : sa ligne est
retirée. Données seulement.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # L'ancienne valeur reste dans le journal (elle avait été portée à 10 jours le 28/10/2026)
    op.execute(
        sa.text(
            """
            INSERT INTO audit_logs (user_id, action, entite, entite_id, ancienne_valeur,
                                    nouvelle_valeur)
            SELECT NULL, 'modification_parametre', 'reconciliation_rule', r.id::text,
                   jsonb_build_object('code', r.code, 'tolerance', r.tolerance::text),
                   jsonb_build_object('code', r.code, 'retire',
                                      'barème fixe des espèces (30/10/2026)')
            FROM reconciliation_rules r WHERE r.code = 'FENETRE_ESPECES'
            """
        )
    )
    op.execute(sa.text("DELETE FROM reconciliation_rules WHERE code = 'FENETRE_ESPECES'"))


def downgrade() -> None:
    op.execute(
        sa.text(
            "INSERT INTO reconciliation_rules (code, libelle, critere, poids, tolerance, actif) "
            "SELECT 'FENETRE_ESPECES', 'Espèces : jours à date pleine autour de l''échéance "
            "Sage', 'fenetre', 0, 2, true WHERE NOT EXISTS (SELECT 1 FROM reconciliation_rules "
            "WHERE code = 'FENETRE_ESPECES')"
        )
    )
