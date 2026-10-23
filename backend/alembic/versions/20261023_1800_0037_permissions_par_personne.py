"""permissions par personne

Revision ID: 0037
Revises: 0036
Create Date: 2026-10-23 18:00:00

Décision du 23/10/2026 : en plus de ses rôles, une personne peut recevoir ou perdre une permission
précise. Ses permissions = celles de ses rôles + ses ajouts − ses retraits. Une ligne par personne
et par permission (`accordee` vrai = ajoutée, faux = retirée), supprimée avec la personne ou la
permission.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_permissions",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.Column("accordee", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_permissions_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name="fk_user_permissions_permission_id_permissions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "permission_id", name="pk_user_permissions"),
    )


def downgrade() -> None:
    op.drop_table("user_permissions")
