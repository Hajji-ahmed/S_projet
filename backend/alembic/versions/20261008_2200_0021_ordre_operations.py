"""ordre des operations

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-08 22:00:00

Un relevé du plus récent au plus ancien est importé dans l'ordre du fichier : l'id ne dit donc pas
quelle opération est la dernière d'un jour (constat du 08/10/2026 sur AWB : le tableau Banques et la
page Relevés lisaient 20 807 737,72 au lieu de 20 351 468,30). `bank_transactions.ordre` garde le
rang chronologique de chaque opération dans son relevé, le même ordre que le calcul des soldes.

Les relevés déjà importés sont rangés ici : si la première ligne importée est plus récente que la
dernière, le fichier allait du plus récent au plus ancien et l'ordre d'import est retourné.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bank_transactions",
        sa.Column("ordre", sa.Integer(), server_default="0", nullable=False),
    )
    op.execute(
        """
        WITH bornes AS (
            SELECT statement_id,
                   (array_agg(date_operation ORDER BY id))[1] AS premiere,
                   (array_agg(date_operation ORDER BY id DESC))[1] AS derniere
            FROM bank_transactions
            GROUP BY statement_id
        ),
        rangs AS (
            SELECT t.id,
                   row_number() OVER (
                       PARTITION BY t.statement_id
                       ORDER BY CASE WHEN b.premiere > b.derniere THEN -t.id ELSE t.id END
                   ) AS rang
            FROM bank_transactions t
            JOIN bornes b ON b.statement_id = t.statement_id
        )
        UPDATE bank_transactions t SET ordre = rangs.rang FROM rangs WHERE rangs.id = t.id
        """
    )


def downgrade() -> None:
    op.drop_column("bank_transactions", "ordre")
