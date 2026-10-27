"""origine « Reprise » d'un rapprochement

Revision ID: 0040
Revises: 0039
Create Date: 2026-10-27 10:00:00

Décision du 27/10/2026 : l'état de rapprochement tenu sous Excel (opérations et écritures encore
non rapprochées à une date) est repris dans SIMTIS. Tout le reste du compte jusqu'à cette date passe
« Rapprochée » dans un seul rapprochement validé, d'origine « Reprise », qui s'équilibre et
s'annule comme les autres (`python -m app.cli reprise-rapprochement`).
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0040"
down_revision: str | None = "0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_reconciliation_matches_origine"), "reconciliation_matches", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_reconciliation_matches_origine"),
        "reconciliation_matches",
        "origine IN ('Automatique', 'Manuelle', 'Frais', 'Reprise')",
    )


def downgrade() -> None:
    op.execute("UPDATE reconciliation_matches SET origine = 'Manuelle' WHERE origine = 'Reprise'")
    op.drop_constraint(
        op.f("ck_reconciliation_matches_origine"), "reconciliation_matches", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_reconciliation_matches_origine"),
        "reconciliation_matches",
        "origine IN ('Automatique', 'Manuelle', 'Frais')",
    )
