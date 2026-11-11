"""compte des commissions 61473000

Revision ID: 0052
Revises: 0051
Create Date: 2026-11-11 12:00:00

Décision du 11/11/2026 : les commissions (COM) des écritures de frais SIMTIS vont au compte général
61473000 (61714000 avant). Le compte des lignes calculées vient du code
(`frais_service.COMPTE_COMMISSION`) ; seules les lignes saisies avant la validation
(`frais_lignes`) le gardent en base.

Données : les lignes saisies sur 61714000 d'une écriture pas encore exportée passent à 61473000,
une ligne d'audit `compte_commission` chacune ; celles d'une écriture déjà exportée gardent
61714000 (Sage les connaît sous ce compte). Le downgrade rend 61714000 aux lignes corrigées, lues
dans l'audit.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0052"
down_revision: str | None = "0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NON_EXPORTEES = """
    FROM frais_lignes l JOIN accounting_entries e ON e.id = l.accounting_entry_id
    WHERE l.compte = '61714000' AND e.exportee_le IS NULL
"""


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO audit_logs (user_id, action, entite, entite_id, ancienne_valeur, nouvelle_valeur)
        SELECT NULL, 'compte_commission', 'frais_ligne', l.id::text,
               jsonb_build_object('compte', l.compte),
               jsonb_build_object('compte', '61473000', 'origine', 'Migration 0052')
        {NON_EXPORTEES}
        ORDER BY l.id
        """
    )
    op.execute(
        f"UPDATE frais_lignes SET compte = '61473000' WHERE id IN (SELECT l.id {NON_EXPORTEES})"
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE frais_lignes SET compte = '61714000'
        WHERE compte = '61473000' AND id::text IN (
            SELECT entite_id FROM audit_logs WHERE action = 'compte_commission'
        )
        """
    )
