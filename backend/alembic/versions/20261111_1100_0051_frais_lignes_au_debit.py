"""lignes de frais saisies au débit

Revision ID: 0051
Revises: 0050
Create Date: 2026-11-11 11:00:00

Décision du 11/11/2026 : une écriture de frais SIMTIS met ses lignes de charge et de TVA au débit
et sa contrepartie au crédit du compte comptable du compte bancaire (au crédit sans ligne banque
depuis le 17/10/2026). La ligne banque est recalculée à la lecture ; seules les lignes saisies
avant la validation (`frais_lignes`) gardent leur sens en base.

Données : les lignes saisies d'une écriture pas encore exportée changent de sens (Crédit ↔ Débit),
une ligne d'audit `sens_lignes_frais` par écriture ; celles d'une écriture déjà exportée ne
changent pas (Sage les connaît ainsi). Le downgrade remet le sens des écritures lues dans l'audit.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0051"
down_revision: str | None = "0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INVERSER = """
    UPDATE frais_lignes
    SET sens = CASE sens WHEN 'Crédit' THEN 'Débit' ELSE 'Crédit' END
    WHERE accounting_entry_id::text IN ({ecritures})
"""


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO audit_logs (user_id, action, entite, entite_id, ancienne_valeur, nouvelle_valeur)
        SELECT NULL, 'sens_lignes_frais', 'accounting_entry', e.id::text,
               jsonb_build_object('lignes', jsonb_agg(
                   jsonb_build_object('compte', l.compte, 'montant', l.montant::text,
                                      'sens', l.sens) ORDER BY l.ordre)),
               jsonb_build_object('lignes', jsonb_agg(
                   jsonb_build_object('compte', l.compte, 'montant', l.montant::text,
                                      'sens', CASE l.sens WHEN 'Crédit' THEN 'Débit'
                                                          ELSE 'Crédit' END) ORDER BY l.ordre),
                                  'origine', 'Migration 0051')
        FROM frais_lignes l JOIN accounting_entries e ON e.id = l.accounting_entry_id
        WHERE e.exportee_le IS NULL
        GROUP BY e.id
        ORDER BY e.id
        """
    )
    op.execute(
        INVERSER.format(
            ecritures="SELECT id::text FROM accounting_entries WHERE exportee_le IS NULL"
        )
    )


def downgrade() -> None:
    op.execute(
        INVERSER.format(
            ecritures="SELECT entite_id FROM audit_logs WHERE action = 'sens_lignes_frais'"
        )
    )
