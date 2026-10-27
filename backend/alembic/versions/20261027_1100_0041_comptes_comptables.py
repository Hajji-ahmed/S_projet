"""plusieurs comptes comptables par compte bancaire

Revision ID: 0041
Revises: 0040
Create Date: 2026-10-27 11:00:00

Décision du 27/10/2026 : un compte bancaire peut porter plusieurs comptes comptables, saisis
« 51410000, 51410100 » et rangés « 51410000,51410100 » (comme les journaux Sage). L'import Sage
garde une ligne dont le compte commence par l'un d'eux ; les frais de SIMTIS passent sur le premier.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "bank_accounts",
        "compte_comptable",
        existing_type=sa.String(length=20),
        type_=sa.String(length=200),
        existing_nullable=True,
    )


def downgrade() -> None:
    # Ne garde que le premier compte, celui des écritures de SIMTIS
    op.execute(
        "UPDATE bank_accounts SET compte_comptable = split_part(compte_comptable, ',', 1) "
        "WHERE compte_comptable LIKE '%,%'"
    )
    op.alter_column(
        "bank_accounts",
        "compte_comptable",
        existing_type=sa.String(length=200),
        type_=sa.String(length=20),
        existing_nullable=True,
    )
