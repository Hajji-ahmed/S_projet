"""famille de frais « frais » (TVA comprise)

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-14 15:00:00

Décision du 14/10/2026 : COMMISSION VIR. RTGS…, COMMISSION REGLEMENT PRELEVEMENT…, COMMISSION
BANCAIRE, COMMISSION TENUE DE COMPTE et FRAIS RECUPERES PAR LA BANQUE sont comptabilisés en
automatique dans une écriture « FRAIS » par jour et par compte, TVA de 10 % calculée (77,50 de frais
récupérés = timbre 50 + 25 + TVA 2,50). La contrainte de famille accepte « frais ».
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AVANT = "('timbres', 'commissions', 'manuelle')"
APRES = "('timbres', 'commissions', 'frais', 'manuelle')"


def _contrainte(familles: str) -> None:
    op.drop_constraint(
        op.f("ck_accounting_entries_famille_frais"), "accounting_entries", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_accounting_entries_famille_frais"),
        "accounting_entries",
        "(origine = 'SIMTIS') = (famille_frais IS NOT NULL) "
        f"AND (famille_frais IS NULL OR famille_frais IN {familles})",
    )


def upgrade() -> None:
    _contrainte(APRES)


def downgrade() -> None:
    # Une écriture « frais » encore là bloquerait le retour : la base la refuse (contrainte)
    _contrainte(AVANT)
