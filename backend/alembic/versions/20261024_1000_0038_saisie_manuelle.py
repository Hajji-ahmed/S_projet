"""saisie manuelle

Revision ID: 0038
Revises: 0037
Create Date: 2026-10-24 10:00:00

Décision du 24/10/2026 : une opération bancaire ou une écriture comptable peut être saisie à la main
(oubli de Sage, opération absente du relevé). Elle a l'origine « Manuelle » et se traite ensuite
comme une ligne importée. La colonne `accounting_entries.origine` passe à 10 caractères.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_bank_transactions_origine"), "bank_transactions", type_="check")
    op.create_check_constraint(
        op.f("ck_bank_transactions_origine"),
        "bank_transactions",
        "origine IN ('Fichier', 'Corrigée', 'Manuelle')",
    )
    op.alter_column(
        "accounting_entries",
        "origine",
        existing_type=sa.String(length=6),
        type_=sa.String(length=10),
        existing_nullable=False,
        existing_server_default="Sage",
    )
    op.drop_constraint(op.f("ck_accounting_entries_origine"), "accounting_entries", type_="check")
    op.create_check_constraint(
        op.f("ck_accounting_entries_origine"),
        "accounting_entries",
        "origine IN ('Sage', 'SIMTIS', 'Manuelle')",
    )


def downgrade() -> None:
    op.execute("UPDATE accounting_entries SET origine = 'Sage' WHERE origine = 'Manuelle'")
    op.execute("UPDATE bank_transactions SET origine = 'Fichier' WHERE origine = 'Manuelle'")
    op.drop_constraint(op.f("ck_accounting_entries_origine"), "accounting_entries", type_="check")
    op.create_check_constraint(
        op.f("ck_accounting_entries_origine"),
        "accounting_entries",
        "origine IN ('Sage', 'SIMTIS')",
    )
    op.alter_column(
        "accounting_entries",
        "origine",
        existing_type=sa.String(length=10),
        type_=sa.String(length=6),
        existing_nullable=False,
        existing_server_default="Sage",
    )
    op.drop_constraint(op.f("ck_bank_transactions_origine"), "bank_transactions", type_="check")
    op.create_check_constraint(
        op.f("ck_bank_transactions_origine"),
        "bank_transactions",
        "origine IN ('Fichier', 'Corrigée')",
    )
