"""compte du droit de timbre 61671000

Revision ID: 0050
Revises: 0049
Create Date: 2026-11-11 10:00:00

Décision du 11/11/2026 : le DT D'ENREGISTREMENT des écritures de frais SIMTIS va au compte général
61671000 (61671 avant). Le compte des lignes calculées vient du code (`frais_service.COMPTE_TIMBRE`) ;
seules les lignes saisies avant la validation (`frais_lignes`) le gardent en base.

Données : les lignes saisies sur 61671 d'une écriture pas encore exportée passent à 61671000, une
ligne d'audit `compte_timbre` chacune ; celles d'une écriture déjà exportée gardent 61671 (Sage les
connaît sous ce compte). Le downgrade rend 61671 aux lignes corrigées, lues dans l'audit.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0050"
down_revision: str | None = "0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NON_EXPORTEES = """
    FROM frais_lignes l JOIN accounting_entries e ON e.id = l.accounting_entry_id
    WHERE l.compte = '61671' AND e.exportee_le IS NULL
"""


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO audit_logs (user_id, action, entite, entite_id, ancienne_valeur, nouvelle_valeur)
        SELECT NULL, 'compte_timbre', 'frais_ligne', l.id::text,
               jsonb_build_object('compte', l.compte),
               jsonb_build_object('compte', '61671000', 'origine', 'Migration 0050')
        {NON_EXPORTEES}
        ORDER BY l.id
        """
    )
    op.execute(
        f"UPDATE frais_lignes SET compte = '61671000' WHERE id IN (SELECT l.id {NON_EXPORTEES})"
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE frais_lignes SET compte = '61671'
        WHERE compte = '61671000' AND id::text IN (
            SELECT entite_id FROM audit_logs WHERE action = 'compte_timbre'
        )
        """
    )
