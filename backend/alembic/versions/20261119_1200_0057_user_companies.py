"""sociétés accessibles par personne

Revision ID: 0057
Revises: 0056
Create Date: 2026-11-19 12:00:00

Décision du 19/11/2026 : l'administrateur peut limiter une personne à certaines sociétés. Une ligne
par personne et par société ; aucune ligne = toutes les sociétés (les comptes existants ne changent
pas) ; le rôle Administrateur voit toujours tout. Supprimée avec la personne ou la société.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0057"
down_revision: str | None = "0056"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_companies",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_companies_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_user_companies_company_id_companies",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "company_id", name="pk_user_companies"),
    )


def downgrade() -> None:
    op.drop_table("user_companies")
