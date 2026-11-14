"""famille de frais « escompte » (FRAIS D'ESCOMPTE)

Revision ID: 0054
Revises: 0053
Create Date: 2026-11-14 10:00:00

Décision du 14/11/2026 : les « INTERET REMISE LCN A L'ESCOMPTE » de BP et leur « TAXE SUR VALEUR
AJOUTEE » sont comptabilisés en automatique dans une famille « FRAIS D'ESCOMPTE » (une écriture par
opération). Les contraintes de famille des écritures SIMTIS et des frais écartés acceptent
« escompte ».

Aucune donnée modifiée. Une écriture ou un écartement « escompte » encore là bloque le downgrade
(la base le refuse).
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0054"
down_revision: str | None = "0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ECRITURES_AVANT = "('timbres', 'commissions', 'frais', 'manuelle')"
ECRITURES_APRES = "('timbres', 'commissions', 'frais', 'escompte', 'manuelle')"
ECARTES_AVANT = "('timbres', 'commissions', 'frais')"
ECARTES_APRES = "('timbres', 'commissions', 'frais', 'escompte')"


def _contraintes(ecritures: str, ecartes: str) -> None:
    op.drop_constraint(
        op.f("ck_accounting_entries_famille_frais"), "accounting_entries", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_accounting_entries_famille_frais"),
        "accounting_entries",
        "(origine = 'SIMTIS') = (famille_frais IS NOT NULL) "
        f"AND (famille_frais IS NULL OR famille_frais IN {ecritures})",
    )
    op.drop_constraint(
        op.f("ck_frais_jours_ecartes_famille_valide"), "frais_jours_ecartes", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_frais_jours_ecartes_famille_valide"),
        "frais_jours_ecartes",
        f"famille IN {ecartes}",
    )


def upgrade() -> None:
    _contraintes(ECRITURES_APRES, ECARTES_APRES)


def downgrade() -> None:
    _contraintes(ECRITURES_AVANT, ECARTES_AVANT)
