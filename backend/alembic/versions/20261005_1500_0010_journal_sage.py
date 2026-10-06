"""journal sage

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-05 15:00:00

Journal de banque Sage de chaque compte bancaire (P10) : rattache une écriture importée de Sage à son
compte bancaire. Un journal ne sert qu'à un compte actif par société.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("bank_accounts", sa.Column("journal_sage", sa.String(length=10), nullable=True))
    op.create_index(
        "uq_bank_accounts_journal_sage_actif",
        "bank_accounts",
        ["company_id", "journal_sage"],
        unique=True,
        postgresql_where=sa.text("journal_sage IS NOT NULL AND actif"),
    )


def downgrade() -> None:
    op.drop_index("uq_bank_accounts_journal_sage_actif", table_name="bank_accounts")
    op.drop_column("bank_accounts", "journal_sage")
