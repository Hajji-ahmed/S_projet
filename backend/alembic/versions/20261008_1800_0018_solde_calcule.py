"""solde calcule

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-08 18:00:00

Relevés sans colonne Solde (décision du 08/10/2026) : SIMTIS calcule le solde de chaque opération
(solde précédent − débit + crédit) et le marque `solde_calcule`. Les opérations déjà importées
gardent `false` ; un relevé déjà importé sans soldes se recalcule avec
`python -m app.cli recalculer-soldes`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bank_transactions",
        sa.Column("solde_calcule", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("bank_transactions", "solde_calcule")
