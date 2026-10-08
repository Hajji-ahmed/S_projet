"""effacer comptes desactives

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-08 10:00:00

Données seulement. Décision du 08/10/2026 : les comptes désactivés sont effacés de la base quand ils
n'ont aucun historique (relevé, opération, écriture, import, contrôle de solde) ; leurs soldes saisis
à la main sont effacés avec eux. Une trace d'audit `suppression_compte` garde ce que contenait chaque
compte. Un compte désactivé qui a un historique reste en base (masqué à l'écran).
Le downgrade ne recrée rien : l'audit garde les valeurs effacées.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SANS_HISTORIQUE = """
    SELECT a.id FROM bank_accounts a
    WHERE NOT a.actif
      AND NOT EXISTS (SELECT 1 FROM bank_statements x WHERE x.bank_account_id = a.id)
      AND NOT EXISTS (SELECT 1 FROM bank_transactions x WHERE x.bank_account_id = a.id)
      AND NOT EXISTS (SELECT 1 FROM accounting_entries x WHERE x.bank_account_id = a.id)
      AND NOT EXISTS (SELECT 1 FROM import_batches x WHERE x.bank_account_id = a.id)
      AND NOT EXISTS (SELECT 1 FROM balance_checks x WHERE x.bank_account_id = a.id)
"""


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            f"""
            INSERT INTO audit_logs (user_id, action, entite, entite_id, ancienne_valeur,
                                    nouvelle_valeur)
            SELECT NULL, 'suppression_compte', 'bank_account', a.id::text,
                   jsonb_build_object(
                       'company_id', a.company_id,
                       'banque', b.code,
                       'libelle', a.libelle,
                       'numero', a.numero,
                       'devise', a.devise,
                       'type_compte', a.type_compte,
                       'journal_sage', a.journal_sage,
                       'credit_autorise', a.credit_autorise::text,
                       'actif', a.actif,
                       'soldes_saisis_effaces',
                           (SELECT count(*) FROM bank_account_balances s
                            WHERE s.bank_account_id = a.id)
                   ),
                   jsonb_build_object('origine', 'Migration 0016')
            FROM bank_accounts a JOIN banks b ON b.id = a.bank_id
            WHERE a.id IN ({SANS_HISTORIQUE})
            """
        )
    )
    connection.execute(
        sa.text(f"DELETE FROM bank_account_balances WHERE bank_account_id IN ({SANS_HISTORIQUE})")
    )
    connection.execute(sa.text(f"DELETE FROM bank_accounts WHERE id IN ({SANS_HISTORIQUE})"))


def downgrade() -> None:
    # Rien n'est recréé : l'audit `suppression_compte` garde les valeurs effacées
    pass
