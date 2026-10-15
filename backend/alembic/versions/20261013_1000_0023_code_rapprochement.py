"""code rapprochement

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-13 10:00:00

Décision du 13/10/2026 : chaque rapprochement validé reçoit un code unique, visible sur toutes ses
lignes (banque et Sage), au format « BANQUE-AA-NNNNNN » (« BP-26-000123 ») : un compteur par compte
bancaire et par année de validation, sans trou ni doublon. Le code est donné à la validation (une
proposition n'en a pas) et reste sur un rapprochement annulé (traçabilité) ; une revalidation est un
nouveau rapprochement, donc un nouveau code. Les rapprochements déjà validés (ou validés puis
annulés) reçoivent ici leur code, dans l'ordre de leur validation.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("reconciliation_matches", sa.Column("code", sa.String(length=30), nullable=True))
    op.create_index(
        "uq_reconciliation_matches_code",
        "reconciliation_matches",
        ["company_id", "code"],
        unique=True,
        postgresql_where=sa.text("code IS NOT NULL"),
    )
    op.create_table(
        "reconciliation_code_counters",
        sa.Column("bank_account_id", sa.Integer(), nullable=False),
        sa.Column("annee", sa.Integer(), nullable=False),
        sa.Column("dernier", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["bank_account_id"],
            ["bank_accounts.id"],
            name="fk_reconciliation_code_counters_bank_account_id_bank_accounts",
        ),
        sa.PrimaryKeyConstraint("bank_account_id", "annee", name="pk_reconciliation_code_counters"),
    )
    # Codes des rapprochements déjà validés : compte de leur première opération, année de validation
    op.execute(
        """
        WITH cibles AS (
            SELECT m.id, m.valide_le,
                   (SELECT t.bank_account_id FROM reconciliation_match_items i
                    JOIN bank_transactions t ON t.id = i.bank_transaction_id
                    WHERE i.match_id = m.id ORDER BY t.id LIMIT 1) AS compte
            FROM reconciliation_matches m
            WHERE m.valide_le IS NOT NULL
        ),
        numerotes AS (
            SELECT c.id, c.compte, EXTRACT(YEAR FROM c.valide_le)::int AS annee,
                   row_number() OVER (
                       PARTITION BY c.compte, EXTRACT(YEAR FROM c.valide_le)
                       ORDER BY c.valide_le, c.id
                   ) AS rang
            FROM cibles c WHERE c.compte IS NOT NULL
        )
        UPDATE reconciliation_matches m
        SET code = b.code || '-' || lpad((n.annee % 100)::text, 2, '0') || '-'
                   || lpad(n.rang::text, 6, '0')
        FROM numerotes n
        JOIN bank_accounts a ON a.id = n.compte
        JOIN banks b ON b.id = a.bank_id
        WHERE m.id = n.id
        """
    )
    op.execute(
        """
        INSERT INTO reconciliation_code_counters (bank_account_id, annee, dernier)
        SELECT t.bank_account_id, EXTRACT(YEAR FROM m.valide_le)::int, count(DISTINCT m.id)
        FROM reconciliation_matches m
        JOIN LATERAL (
            SELECT tr.bank_account_id FROM reconciliation_match_items i
            JOIN bank_transactions tr ON tr.id = i.bank_transaction_id
            WHERE i.match_id = m.id ORDER BY tr.id LIMIT 1
        ) t ON true
        WHERE m.code IS NOT NULL
        GROUP BY 1, 2
        """
    )


def downgrade() -> None:
    op.drop_table("reconciliation_code_counters")
    op.drop_index("uq_reconciliation_matches_code", table_name="reconciliation_matches")
    op.drop_column("reconciliation_matches", "code")
