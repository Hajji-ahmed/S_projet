"""societe tefil

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-05 10:00:00

Migration de données seulement. Le nom de la 2e société est confirmé le 05/10/2026 : « Société X »
devient « Tefil ». Le code `SOCX` ne change pas (les seeds retrouvent la société par son code). Un
nom déjà changé par un utilisateur n'est jamais écrasé. Le retour arrière ne défait rien.
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    company_id = connection.execute(
        text(
            "UPDATE companies SET nom = 'Tefil', updated_at = now() "
            "WHERE code = 'SOCX' AND nom = 'Société X' RETURNING id"
        )
    ).scalar()
    if company_id is not None:
        connection.execute(
            text(
                "INSERT INTO audit_logs (user_id, action, entite, entite_id, ancienne_valeur, "
                "nouvelle_valeur) VALUES (NULL, 'renommage_societe', 'company', :id, "
                """'{"nom": "Société X"}'::jsonb, '{"nom": "Tefil"}'::jsonb)"""
            ),
            {"id": company_id},
        )


def downgrade() -> None:
    # Rien à défaire : le nom confirmé reste le bon.
    pass
