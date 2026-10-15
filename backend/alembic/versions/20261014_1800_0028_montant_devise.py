"""montant en devise des écritures Sage

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-14 18:00:00

Décision du 14/10/2026 : le grand livre Sage d'un compte en devise (EUR, USD) a une colonne de plus,
« Devise », le montant en devise de la ligne (débit et crédit restent en MAD). Il est gardé avec le
même sens que la ligne, et c'est lui qui se rapproche du relevé du compte, tenu dans sa devise.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "accounting_entries", sa.Column("montant_devise", sa.Numeric(18, 2), nullable=True)
    )
    op.create_check_constraint(
        op.f("ck_accounting_entries_devise_meme_sens"),
        "accounting_entries",
        "montant_devise IS NULL OR montant_devise * montant > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_accounting_entries_devise_meme_sens"), "accounting_entries", type_="check"
    )
    op.drop_column("accounting_entries", "montant_devise")
