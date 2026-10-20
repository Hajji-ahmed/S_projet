"""operations en cours

Revision ID: 0033
Revises: 0032
Create Date: 2026-10-20 10:00:00

Décision du 20/10/2026 : une ligne de relevé dont le libellé finit par « (*) » est une opération en
cours (déjà dans le solde de la banque, pas encore définitive) : `en_cours`, jamais rapprochée. À
l'import de sa définitive (même compte, montant et libellé sans « (*) », à 10 jours au plus), elle
est remplacée : `remplacee_par_id` pointe la définitive, elle garde son solde.

Données : les opérations déjà importées dont le libellé finit par « (*) » passent en cours.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bank_transactions",
        sa.Column("en_cours", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column("bank_transactions", sa.Column("remplacee_par_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_bank_transactions_remplacee_par_id_bank_transactions"),
        "bank_transactions",
        "bank_transactions",
        ["remplacee_par_id"],
        ["id"],
    )
    op.create_check_constraint(
        op.f("ck_bank_transactions_remplacee_si_en_cours"),
        "bank_transactions",
        "remplacee_par_id IS NULL OR en_cours",
    )
    op.execute(
        r"UPDATE bank_transactions SET en_cours = true "
        r"WHERE libelle ~ '\(\s*\*\s*\)\s*$' AND statut = 'Non rapprochée'"
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_bank_transactions_remplacee_si_en_cours"), "bank_transactions", type_="check"
    )
    op.drop_constraint(
        op.f("fk_bank_transactions_remplacee_par_id_bank_transactions"),
        "bank_transactions",
        type_="foreignkey",
    )
    op.drop_column("bank_transactions", "remplacee_par_id")
    op.drop_column("bank_transactions", "en_cours")
