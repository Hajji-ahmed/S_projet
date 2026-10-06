"""rapprochement actif

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-06 10:00:00

Rapprochement 1→1 (P11). Une opération bancaire, et de même une écriture comptable, ne fait partie que
d'UNE correspondance active (« Proposée » ou « Validée ») : `actif` est porté par l'élément et deux index
uniques partiels le garantissent en base. `detail_score` garde les points obtenus par critère.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "reconciliation_match_items",
        sa.Column("actif", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "reconciliation_matches",
        sa.Column("detail_score", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index(
        "uq_reconciliation_match_items_transaction_active",
        "reconciliation_match_items",
        ["bank_transaction_id"],
        unique=True,
        postgresql_where=sa.text("actif AND bank_transaction_id IS NOT NULL"),
    )
    op.create_index(
        "uq_reconciliation_match_items_ecriture_active",
        "reconciliation_match_items",
        ["accounting_entry_id"],
        unique=True,
        postgresql_where=sa.text("actif AND accounting_entry_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_reconciliation_match_items_ecriture_active", table_name="reconciliation_match_items"
    )
    op.drop_index(
        "uq_reconciliation_match_items_transaction_active", table_name="reconciliation_match_items"
    )
    op.drop_column("reconciliation_matches", "detail_score")
    op.drop_column("reconciliation_match_items", "actif")
