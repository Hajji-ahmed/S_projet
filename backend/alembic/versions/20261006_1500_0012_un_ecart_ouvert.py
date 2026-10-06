"""un ecart ouvert

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-06 15:00:00

Écarts (P12) : une opération bancaire, et de même une écriture comptable, n'a qu'UN écart ouvert
(statut autre que « Clôturé ») à la fois. Deux index uniques partiels le garantissent en base.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_discrepancies_transaction_ouvert",
        "discrepancies",
        ["bank_transaction_id"],
        unique=True,
        postgresql_where=sa.text("statut <> 'Clôturé' AND bank_transaction_id IS NOT NULL"),
    )
    op.create_index(
        "uq_discrepancies_ecriture_ouvert",
        "discrepancies",
        ["accounting_entry_id"],
        unique=True,
        postgresql_where=sa.text("statut <> 'Clôturé' AND accounting_entry_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_discrepancies_ecriture_ouvert", table_name="discrepancies")
    op.drop_index("uq_discrepancies_transaction_ouvert", table_name="discrepancies")
