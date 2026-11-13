"""frais écartés par opération

Revision ID: 0053
Revises: 0052
Create Date: 2026-11-13 10:00:00

Décision du 13/11/2026 : une écriture de frais SIMTIS par opération du relevé (plus une par jour).
« Écarter » porte donc sur une opération : `frais_jours_ecartes.bank_transaction_id` (nullable,
supprimé avec l'opération). Une ligne sans opération reste une journée entière écartée (lignes
d'avant le 13/11/2026) ; l'unicité (compte, jour, famille) ne vaut plus que pour elles (index
partiel), une opération ne s'écarte qu'une fois.

Aucune donnée modifiée. Le downgrade supprime les écartements par opération (leurs frais sont de
nouveau proposés), puis la colonne.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0053"
down_revision: str | None = "0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "frais_jours_ecartes", sa.Column("bank_transaction_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_frais_jours_ecartes_bank_transaction_id_bank_transactions"),
        "frais_jours_ecartes",
        "bank_transactions",
        ["bank_transaction_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_frais_jours_ecartes_operation", "frais_jours_ecartes", ["bank_transaction_id"]
    )
    op.drop_constraint(
        "uq_frais_jours_ecartes_compte_jour_famille", "frais_jours_ecartes", type_="unique"
    )
    op.create_index(
        "uq_frais_jours_ecartes_compte_jour_famille",
        "frais_jours_ecartes",
        ["bank_account_id", "jour", "famille"],
        unique=True,
        postgresql_where=sa.text("bank_transaction_id IS NULL"),
    )


def downgrade() -> None:
    op.execute("DELETE FROM frais_jours_ecartes WHERE bank_transaction_id IS NOT NULL")
    op.drop_index("uq_frais_jours_ecartes_compte_jour_famille", table_name="frais_jours_ecartes")
    op.create_unique_constraint(
        "uq_frais_jours_ecartes_compte_jour_famille",
        "frais_jours_ecartes",
        ["bank_account_id", "jour", "famille"],
    )
    op.drop_constraint("uq_frais_jours_ecartes_operation", "frais_jours_ecartes", type_="unique")
    op.drop_constraint(
        op.f("fk_frais_jours_ecartes_bank_transaction_id_bank_transactions"),
        "frais_jours_ecartes",
        type_="foreignkey",
    )
    op.drop_column("frais_jours_ecartes", "bank_transaction_id")
