"""solde comptable d'ouverture

Revision ID: 0039
Revises: 0038
Create Date: 2026-10-26 10:00:00

Décision du 26/10/2026 : le solde comptable (Sage) d'un compte bancaire se calcule à partir d'un solde
d'ouverture saisi une fois, à une date (ex. le grand livre au 31/12/2025), plus les écritures
importées après cette date. Pour un compte EUR / USD, le même solde dans la devise du compte.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("bank_accounts", sa.Column("date_solde_comptable", sa.Date(), nullable=True))
    op.add_column(
        "bank_accounts",
        sa.Column("solde_comptable_ouverture", sa.Numeric(precision=18, scale=2), nullable=True),
    )
    op.add_column(
        "bank_accounts",
        sa.Column(
            "solde_comptable_ouverture_devise", sa.Numeric(precision=18, scale=2), nullable=True
        ),
    )
    # Un solde d'ouverture va toujours avec sa date
    op.create_check_constraint(
        op.f("ck_bank_accounts_solde_comptable_date"),
        "bank_accounts",
        "(date_solde_comptable IS NULL) = (solde_comptable_ouverture IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_bank_accounts_solde_comptable_date"), "bank_accounts", type_="check"
    )
    op.drop_column("bank_accounts", "solde_comptable_ouverture_devise")
    op.drop_column("bank_accounts", "solde_comptable_ouverture")
    op.drop_column("bank_accounts", "date_solde_comptable")
