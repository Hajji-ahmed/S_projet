"""agios d'escompte CIH sur 63117000

Revision ID: 0058
Revises: 0057
Create Date: 2026-11-19 14:00:00

Décision du 19/11/2026 : les agios d'escompte LCN de CIH (écriture automatique « FRAIS ») vont au
compte 63117000 FRAIS D'ESCOMPTE (63116300 AGIOS CIH avant). Le compte des lignes calculées vient
du code (`frais_service.COMPTE_PAR_TYPE`) ; seules les lignes saisies avant la validation
(`frais_lignes`) le gardent en base.

Données : les lignes saisies sur 63116300 des écritures SIMTIS automatiques « frais » d'un compte
CIH passent à 63117000, **exportées ou non** (choix du métier), une ligne d'audit
`compte_agios_escompte` chacune. Les écritures manuelles (AGIOS CIH à la main) ne bougent pas. Le
downgrade rend 63116300 aux lignes corrigées, lues dans l'audit.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0058"
down_revision: str | None = "0057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LIGNES = """
    FROM frais_lignes l
    JOIN accounting_entries e ON e.id = l.accounting_entry_id
    JOIN bank_accounts a ON a.id = e.bank_account_id
    JOIN banks b ON b.id = a.bank_id
    WHERE l.compte = '63116300' AND e.origine = 'SIMTIS' AND e.famille_frais = 'frais'
      AND b.code = 'CIH'
"""


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO audit_logs (user_id, action, entite, entite_id, ancienne_valeur, nouvelle_valeur)
        SELECT NULL, 'compte_agios_escompte', 'frais_ligne', l.id::text,
               jsonb_build_object('compte', l.compte),
               jsonb_build_object('compte', '63117000', 'origine', 'Migration 0058')
        {LIGNES}
        ORDER BY l.id
        """
    )
    op.execute(f"UPDATE frais_lignes SET compte = '63117000' WHERE id IN (SELECT l.id {LIGNES})")


def downgrade() -> None:
    op.execute(
        """
        UPDATE frais_lignes SET compte = '63116300'
        WHERE compte = '63117000' AND id::text IN (
            SELECT entite_id FROM audit_logs WHERE action = 'compte_agios_escompte'
        )
        """
    )
