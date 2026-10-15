"""comptes des commissions

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-13 18:00:00

Décision du 13/10/2026 : SIMTIS comptabilise aussi les commissions du relevé, une écriture « COM »
par jour et par compte, une ligne par type (commission, TVA, commission effet, TVA de la commission
effet). Leurs comptes Sage, pour l'export, sont portés par le compte bancaire, comme le compte de
charge des timbres (migration 0024).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLONNES = ("compte_commission", "compte_commission_effet", "compte_tva")


def upgrade() -> None:
    for colonne in COLONNES:
        op.add_column("bank_accounts", sa.Column(colonne, sa.String(length=20), nullable=True))


def downgrade() -> None:
    for colonne in reversed(COLONNES):
        op.drop_column("bank_accounts", colonne)
