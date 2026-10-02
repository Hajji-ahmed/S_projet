"""pointage automatique des operations deja importees

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-02 14:00:00

Migration de données seulement (aucun changement de schéma). Le Pointage vide des opérations
importées avant la règle automatique (décision métier du 02/10/2026) est rempli une seule fois,
avec la même règle que `normalization_service.guess_pointage` :
COMMISSION, AGIOS, FRAIS, TENUE DE COMPTE → Frais bancaires ; sinon crédit → Encaissement,
débit → Décaissement. Un Pointage déjà renseigné n'est jamais modifié.
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FILL = text(
    r"""
    UPDATE bank_transactions AS t
    SET pointage_type_id = p.id
    FROM pointage_types AS p
    WHERE t.pointage_type_id IS NULL
      AND p.actif
      AND p.code = CASE
            WHEN upper(t.libelle) ~ '\m(COMMISSIONS?|AGIOS|FRAIS|TENUE DE COMPTE)\M'
                THEN 'FRAIS_BANCAIRES'
            WHEN t.credit > 0 THEN 'ENCAISSEMENT'
            WHEN t.debit > 0 THEN 'DECAISSEMENT'
          END
    """
)

AUDIT = text(
    """
    INSERT INTO audit_logs (user_id, action, entite, nouvelle_valeur)
    VALUES (NULL, 'remplissage_pointage', 'bank_transaction',
            jsonb_build_object('migration', '0005', 'operations', CAST(:count AS integer)))
    """
)


def upgrade() -> None:
    connection = op.get_bind()
    count = connection.execute(FILL).rowcount
    if count:
        connection.execute(AUDIT, {"count": count})


def downgrade() -> None:
    # Rien à défaire : on ne peut pas distinguer ces pointages d'un pointage saisi ensuite.
    pass
