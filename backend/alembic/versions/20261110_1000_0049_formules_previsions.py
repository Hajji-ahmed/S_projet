"""formule gardee dans les cellules de montant des previsions

Revision ID: 0049
Revises: 0048
Create Date: 2026-11-10 10:00:00

Décision du 10/11/2026 : une cellule de montant du tableau Prévisions saisie avec une formule
(« =1000+500+250 ») garde sa formule à côté du résultat, pour la revoir et la corriger. Le montant
reste la seule valeur qui compte. Une formule n'existe jamais sans son montant (CHECK).

Données : aucune ; les formules d'avant n'ont pas été gardées, ces cellules restent des montants.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0049"
down_revision: str | None = "0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLONNES_JOUR = ("formule_encaissement", "formule_escompte", "formule_douane")


def upgrade() -> None:
    op.add_column("saisies_previsions", sa.Column("formule", sa.String(200), nullable=True))
    # L'autogénération ne voit pas les CHECK : ajoutés à la main (tests dans test_constraints.py)
    op.create_check_constraint(
        op.f("ck_saisies_previsions_formule_avec_montant"),
        "saisies_previsions",
        "formule IS NULL OR montant IS NOT NULL",
    )
    for colonne in COLONNES_JOUR:
        op.add_column("saisies_previsions_jour", sa.Column(colonne, sa.String(200), nullable=True))
    op.create_check_constraint(
        op.f("ck_saisies_previsions_jour_formules_avec_montants"),
        "saisies_previsions_jour",
        "(formule_encaissement IS NULL OR encaissement IS NOT NULL)"
        " AND (formule_escompte IS NULL OR escompte IS NOT NULL)"
        " AND (formule_douane IS NULL OR douane IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_saisies_previsions_jour_formules_avec_montants"),
        "saisies_previsions_jour",
        type_="check",
    )
    for colonne in COLONNES_JOUR:
        op.drop_column("saisies_previsions_jour", colonne)
    op.drop_constraint(
        op.f("ck_saisies_previsions_formule_avec_montant"), "saisies_previsions", type_="check"
    )
    op.drop_column("saisies_previsions", "formule")
