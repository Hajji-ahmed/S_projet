"""frais comptabilisés à la main

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-14 09:00:00

Décision du 13/10/2026 : les frais restés dans « À comptabiliser » sans être pris en automatique
(agios, intérêts, commissions RTGS…) peuvent être comptabilisés à la main dans SIMTIS : l'utilisateur
coche des opérations d'un compte, saisit le libellé et la date, et peut séparer le frais de sa TVA.

- `accounting_entries.famille_frais` : famille d'une écriture SIMTIS (timbres, commissions,
  manuelle) ; le libellé d'une écriture manuelle étant libre, il ne la désigne plus. Les écritures
  déjà créées la reçoivent d'après leur libellé ;
- `montant_tva` (positif, strictement inférieur au montant) et `taux_tva` (en %, pour l'historique),
  seulement pour une écriture manuelle.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "accounting_entries", sa.Column("famille_frais", sa.String(length=12), nullable=True)
    )
    op.add_column("accounting_entries", sa.Column("montant_tva", sa.Numeric(18, 2), nullable=True))
    op.add_column("accounting_entries", sa.Column("taux_tva", sa.Numeric(6, 2), nullable=True))
    op.execute(
        "UPDATE accounting_entries SET famille_frais = CASE libelle "
        "WHEN 'COM' THEN 'commissions' ELSE 'timbres' END WHERE origine = 'SIMTIS'"
    )
    op.create_check_constraint(
        op.f("ck_accounting_entries_famille_frais"),
        "accounting_entries",
        "(origine = 'SIMTIS') = (famille_frais IS NOT NULL) "
        "AND (famille_frais IS NULL OR famille_frais IN ('timbres', 'commissions', 'manuelle'))",
    )
    op.create_check_constraint(
        op.f("ck_accounting_entries_tva_manuelle"),
        "accounting_entries",
        "montant_tva IS NULL OR (famille_frais = 'manuelle' AND montant_tva > 0 "
        "AND montant_tva < abs(montant))",
    )
    op.create_check_constraint(
        op.f("ck_accounting_entries_taux_tva"),
        "accounting_entries",
        "taux_tva IS NULL OR (montant_tva IS NOT NULL AND taux_tva > 0 AND taux_tva <= 100)",
    )


def downgrade() -> None:
    for nom in ("taux_tva", "tva_manuelle", "famille_frais"):
        op.drop_constraint(
            op.f(f"ck_accounting_entries_{nom}"), "accounting_entries", type_="check"
        )
    op.drop_column("accounting_entries", "taux_tva")
    op.drop_column("accounting_entries", "montant_tva")
    op.drop_column("accounting_entries", "famille_frais")
