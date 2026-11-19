"""pièce des frais AWB en AW

Revision ID: 0056
Revises: 0055
Create Date: 2026-11-19 10:00:00

Décision du 19/11/2026 : le N° pièce des écritures de frais AWB s'écrit « AW2610098 », sans le B
(`frais_service.PREFIXES_PIECE`). Les écritures SIMTIS déjà exportées sous « AWB » + 7 chiffres sont
renommées « AW » + les mêmes 7 chiffres, avec une ligne d'audit `renumerotation_piece` chacune. Les
écritures venues de Sage et les autres banques ne bougent pas. Le downgrade fait le chemin inverse
(sans audit : les deux n° restent dans l'audit de l'upgrade).
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0056"
down_revision: str | None = "0055"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        r"""
        INSERT INTO audit_logs (user_id, action, entite, entite_id, ancienne_valeur, nouvelle_valeur)
        SELECT NULL, 'renumerotation_piece', 'accounting_entry', id::text,
               jsonb_build_object('numero_piece', numero_piece),
               jsonb_build_object('numero_piece', 'AW' || substr(numero_piece, 4),
                                  'origine', 'Migration 0056')
        FROM accounting_entries
        WHERE origine = 'SIMTIS' AND numero_piece ~ '^AWB\d{7}$'
        ORDER BY id
        """
    )
    op.execute(
        r"""
        UPDATE accounting_entries SET numero_piece = 'AW' || substr(numero_piece, 4)
        WHERE origine = 'SIMTIS' AND numero_piece ~ '^AWB\d{7}$'
        """
    )


def downgrade() -> None:
    op.execute(
        r"""
        UPDATE accounting_entries SET numero_piece = 'AWB' || substr(numero_piece, 3)
        WHERE origine = 'SIMTIS' AND numero_piece ~ '^AW\d{7}$'
          AND EXISTS (
              SELECT 1 FROM bank_accounts a JOIN banks b ON b.id = a.bank_id
              WHERE a.id = accounting_entries.bank_account_id AND b.code = 'AWB'
          )
        """
    )
