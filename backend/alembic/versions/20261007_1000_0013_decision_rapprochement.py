"""decision rapprochement

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-07 10:00:00

Historique des rapprochements : chaque décision (validation, rejet, annulation) garde son auteur et sa
date sur la correspondance (`decide_par_id`, `decide_le`). Les décisions passées sont reprises de
`valide_par_id` / `valide_le`, sinon de l'historique d'audit (dernière décision tracée).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("reconciliation_matches", sa.Column("decide_par_id", sa.Integer(), nullable=True))
    op.add_column(
        "reconciliation_matches",
        sa.Column("decide_le", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_reconciliation_matches_decide_par_id_users"),
        "reconciliation_matches",
        "users",
        ["decide_par_id"],
        ["id"],
    )
    op.create_index(
        "ix_reconciliation_matches_societe_decision",
        "reconciliation_matches",
        ["company_id", "decide_le"],
    )
    # Reprise : la validation est déjà sur la correspondance ; le rejet et l'annulation sont dans l'audit
    op.execute(
        """
        UPDATE reconciliation_matches
        SET decide_par_id = valide_par_id, decide_le = valide_le
        WHERE statut = 'Validée'
        """
    )
    op.execute(
        """
        UPDATE reconciliation_matches m
        SET decide_par_id = a.user_id, decide_le = a.created_at
        FROM (
            SELECT DISTINCT ON (entite_id) entite_id, user_id, created_at
            FROM audit_logs
            WHERE entite = 'reconciliation_match'
              AND action IN ('rejet_rapprochement', 'annulation_rapprochement')
            ORDER BY entite_id, id DESC
        ) a
        WHERE m.statut IN ('Rejetée', 'Annulée') AND a.entite_id = m.id::text
        """
    )
    op.create_check_constraint(
        "decision_tracee",
        "reconciliation_matches",
        "statut = 'Proposée' OR (decide_par_id IS NOT NULL AND decide_le IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("decision_tracee", "reconciliation_matches", type_="check")
    op.drop_index("ix_reconciliation_matches_societe_decision", table_name="reconciliation_matches")
    op.drop_constraint(
        op.f("fk_reconciliation_matches_decide_par_id_users"),
        "reconciliation_matches",
        type_="foreignkey",
    )
    op.drop_column("reconciliation_matches", "decide_le")
    op.drop_column("reconciliation_matches", "decide_par_id")
