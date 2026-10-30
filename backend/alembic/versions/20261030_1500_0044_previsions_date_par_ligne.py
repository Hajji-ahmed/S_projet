"""previsions : une date par ligne

Revision ID: 0044
Revises: 0043
Create Date: 2026-10-30 15:00:00

Décision du 30/10/2026 : chaque ligne du tableau Prévisions a sa propre date, et la Trésorerie
ajoute ou supprime des lignes (plus de bloc fixe de 14 lignes). `jour` devient la date de la ligne
et `ligne` son rang parmi les lignes de cette date : la limite passe de 14 à 99 lignes par date.
Les lignes déjà saisies gardent comme date le jour où elles ont été saisies (aucune donnée
déplacée). Le retour arrière refuse de perdre des lignes au-delà de la 14e.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0044"
down_revision: str | None = "0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("saisies_previsions", "saisies_previsions_jour")


def _limite(maximum: int) -> None:
    # L'autogénération ne voit pas les CHECK (tests dans test_constraints.py)
    for table in TABLES:
        op.drop_constraint(op.f(f"ck_{table}_ligne_du_bloc"), table, type_="check")
        op.create_check_constraint(
            op.f(f"ck_{table}_ligne_du_bloc"), table, f"ligne BETWEEN 1 AND {maximum}"
        )


def upgrade() -> None:
    _limite(99)


def downgrade() -> None:
    bind = op.get_bind()
    lost = sum(
        bind.scalar(sa.text(f"SELECT count(*) FROM {table} WHERE ligne > 14")) for table in TABLES
    )
    if lost:
        raise RuntimeError(
            f"{lost} cellule(s) Prévisions au-delà de la 14e ligne d'une date : "
            "le retour arrière les perdrait. Supprimez ces lignes d'abord."
        )
    _limite(14)
