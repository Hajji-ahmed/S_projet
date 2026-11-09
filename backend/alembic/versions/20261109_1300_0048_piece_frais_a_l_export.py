"""numero de piece des frais donne a l'export

Revision ID: 0048
Revises: 0047
Create Date: 2026-11-09 13:00:00

Décision du 09/11/2026 : une écriture de frais créée par SIMTIS (automatique ou manuelle) n'a plus
de N° pièce à sa validation ; elle le reçoit à l'export vers Sage, où le comptable donne le N° de la
première pièce de la banque et du mois (« BP2610001 ») et les suivantes se numérotent à la suite.
Le compteur `frais_piece_counters` n'est plus utilisé (la table reste).

Données : les écritures SIMTIS pas encore exportées perdent leur N° pièce, une ligne d'audit
`piece_a_l_export` chacune (l'ancien n° y reste) ; celles déjà exportées gardent le leur (Sage les
connaît sous ce n°). Le downgrade ne rend pas les anciens n° : ils restent dans l'audit.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0048"
down_revision: str | None = "0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO audit_logs (user_id, action, entite, entite_id, ancienne_valeur, nouvelle_valeur)
        SELECT NULL, 'piece_a_l_export', 'accounting_entry', id::text,
               jsonb_build_object('numero_piece', numero_piece),
               jsonb_build_object('numero_piece', NULL, 'origine', 'Migration 0048')
        FROM accounting_entries
        WHERE origine = 'SIMTIS' AND exportee_le IS NULL AND numero_piece IS NOT NULL
        ORDER BY id
        """
    )
    op.execute(
        "UPDATE accounting_entries SET numero_piece = NULL "
        "WHERE origine = 'SIMTIS' AND exportee_le IS NULL AND numero_piece IS NOT NULL"
    )


def downgrade() -> None:
    # Les anciens n° ne reviennent pas (ils sont dans l'audit `piece_a_l_export`)
    pass
