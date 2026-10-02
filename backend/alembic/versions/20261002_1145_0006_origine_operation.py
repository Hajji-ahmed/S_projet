"""origine operation

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-02 11:45:02.990579

Origine d'une opération bancaire : « Fichier » (telle que le relevé) ou « Corrigée » (modifiée dans
l'aperçu avant l'enregistrement). Les opérations existantes prennent « Fichier ».
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bank_transactions",
        sa.Column("origine", sa.String(length=10), server_default="Fichier", nullable=False),
    )
    # L'autogénération ne voit pas les CHECK : ajouté à la main (test dans test_constraints.py)
    op.create_check_constraint(
        op.f("ck_bank_transactions_origine"),
        "bank_transactions",
        "origine IN ('Fichier', 'Corrigée')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_bank_transactions_origine"), "bank_transactions", type_="check")
    op.drop_column("bank_transactions", "origine")
