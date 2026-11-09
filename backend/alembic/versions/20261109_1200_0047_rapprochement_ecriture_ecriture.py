"""rapprochement d'une écriture avec une écriture (type « E-E »)

Revision ID: 0047
Revises: 0046
Create Date: 2026-11-09 12:00:00

Décision du 09/11/2026 : un impayé Sage (« IMP … », « IMPAYE … ») et l'écriture d'origine
qu'il annule (chèque ou effet, même numéro, même montant de sens opposé, même compte) se
rapprochent entre eux, sans opération de banque. La correspondance a le type « E-E » ; ses deux
éléments sont des écritures. Le retour arrière s'arrête s'il en existe une : elles se traitent
avant, rien n'est supprimé en silence.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0047"
down_revision: str | None = "0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AVANT = "type IN ('1-1', '1-N', 'N-1', 'N-N')"
APRES = "type IN ('1-1', '1-N', 'N-1', 'N-N', 'E-E')"


def upgrade() -> None:
    # L'autogénération ne voit pas les CHECK : test dans test_constraints.py
    op.drop_constraint(
        op.f("ck_reconciliation_matches_type"), "reconciliation_matches", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_reconciliation_matches_type"), "reconciliation_matches", APRES
    )


def downgrade() -> None:
    nb = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM reconciliation_matches WHERE type = 'E-E'"))
        .scalar_one()
    )
    if nb:
        raise RuntimeError(
            f"{nb} rapprochement(s) écriture ↔ écriture : supprimez-les avant le retour arrière."
        )
    op.drop_constraint(
        op.f("ck_reconciliation_matches_type"), "reconciliation_matches", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_reconciliation_matches_type"), "reconciliation_matches", AVANT
    )
