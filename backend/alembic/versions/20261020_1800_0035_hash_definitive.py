"""empreinte de la ligne definitive

Revision ID: 0035
Revises: 0034
Create Date: 2026-10-20 18:00:00

Décision du 20/10/2026 : une opération « (*) » du relevé n'est plus doublée par sa définitive, elle
est complétée par elle (libellé, date de valeur, référence) ; `hash_definitive` garde l'empreinte de
la ligne définitive pour qu'un réimport de son relevé la reconnaisse.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bank_transactions", sa.Column("hash_definitive", sa.String(length=64), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("bank_transactions", "hash_definitive")
