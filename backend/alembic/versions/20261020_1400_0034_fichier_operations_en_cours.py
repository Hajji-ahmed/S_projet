"""fichier des operations en cours

Revision ID: 0034
Revises: 0033
Create Date: 2026-10-20 14:00:00

Décision du 20/10/2026 : certaines banques envoient leurs opérations en cours dans un fichier à
part, alors qu'elles sont déjà dans leur solde. Un tel fichier s'importe comme un relevé marqué
`en_cours` : ses lignes sont en cours, sans solde, et leur montant s'ajoute au solde du compte
jusqu'à l'arrivée de leur définitive.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bank_statements",
        sa.Column("en_cours", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("bank_statements", "en_cours")
