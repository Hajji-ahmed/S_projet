"""previsions par ligne

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-03 15:00:00

Encaissement, Escompte et Douane du tableau Prévisions se saisissent ligne par ligne (décision du
03/10/2026) au lieu d'une valeur pour toute la journée. Les valeurs existantes sont placées sur la
ligne 1, sans perte. Le retour arrière refuse de perdre des montants saisis sur d'autres lignes.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "saisies_previsions_jour",
        sa.Column("ligne", sa.SmallInteger(), server_default="1", nullable=False),
    )
    # La valeur par défaut ne sert qu'aux lignes existantes : l'application donne toujours la ligne
    op.alter_column("saisies_previsions_jour", "ligne", server_default=None)
    op.drop_constraint(
        "uq_saisies_previsions_jour_societe_jour", "saisies_previsions_jour", type_="unique"
    )
    op.create_unique_constraint(
        "uq_saisies_previsions_jour_societe_jour_ligne",
        "saisies_previsions_jour",
        ["company_id", "jour", "ligne"],
    )
    # L'autogénération ne voit pas les CHECK : ajouté à la main (test dans test_constraints.py)
    op.create_check_constraint(
        op.f("ck_saisies_previsions_jour_ligne_du_bloc"),
        "saisies_previsions_jour",
        "ligne BETWEEN 1 AND 14",
    )


def downgrade() -> None:
    lost = op.get_bind().scalar(
        sa.text("SELECT count(*) FROM saisies_previsions_jour WHERE ligne <> 1")
    )
    if lost:
        raise RuntimeError(
            f"{lost} montant(s) Encaissement / Escompte / Douane saisi(s) hors de la ligne 1 : "
            "le retour arrière les perdrait. Videz ces cellules d'abord."
        )
    op.drop_constraint(
        op.f("ck_saisies_previsions_jour_ligne_du_bloc"), "saisies_previsions_jour", type_="check"
    )
    op.drop_constraint(
        "uq_saisies_previsions_jour_societe_jour_ligne", "saisies_previsions_jour", type_="unique"
    )
    op.create_unique_constraint(
        "uq_saisies_previsions_jour_societe_jour",
        "saisies_previsions_jour",
        ["company_id", "jour"],
    )
    op.drop_column("saisies_previsions_jour", "ligne")
