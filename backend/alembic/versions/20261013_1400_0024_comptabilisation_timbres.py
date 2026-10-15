"""comptabilisation des droits de timbre

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-13 14:00:00

Décision du 13/10/2026 : les droits de timbre du relevé (DROIT(S) DE TIMBRE…) sont comptabilisés
par SIMTIS, une écriture « DT D'ENREGISTREMENT » par jour et par compte bancaire. Mustapha valide :
l'écriture (ligne banque) est enregistrée avec l'origine SIMTIS et rapprochée tout de suite de ses
timbres ; elle s'exporte ensuite pour Sage (`exportee_le`).

- `bank_accounts.journal_frais` (journal Sage des frais, 5543 pour BP) et `compte_timbre` (compte de
  charge des timbres, fourni par la comptabilité) ;
- `accounting_entries.origine` (Sage / SIMTIS) et `exportee_le` (SIMTIS seulement) ;
- origine « Frais » d'une correspondance ;
- permission `accounting.prepare`, donnée aux rôles Administrateur et Comptable existants (les seeds
  n'appliquent les permissions qu'à la création d'un rôle).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSION = "accounting.prepare"
DESCRIPTION = "Comptabiliser les frais bancaires (écritures préparées par SIMTIS)"


def upgrade() -> None:
    op.add_column("bank_accounts", sa.Column("journal_frais", sa.String(length=10), nullable=True))
    op.add_column("bank_accounts", sa.Column("compte_timbre", sa.String(length=20), nullable=True))

    op.add_column(
        "accounting_entries",
        sa.Column("origine", sa.String(length=6), server_default="Sage", nullable=False),
    )
    op.add_column(
        "accounting_entries",
        sa.Column("exportee_le", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_accounting_entries_origine"),
        "accounting_entries",
        "origine IN ('Sage', 'SIMTIS')",
    )
    op.create_check_constraint(
        op.f("ck_accounting_entries_export_simtis"),
        "accounting_entries",
        "exportee_le IS NULL OR origine = 'SIMTIS'",
    )
    op.create_index(
        "ix_accounting_entries_simtis",
        "accounting_entries",
        ["company_id", "date_ecriture"],
        postgresql_where=sa.text("origine = 'SIMTIS'"),
    )

    op.drop_constraint(
        op.f("ck_reconciliation_matches_origine"), "reconciliation_matches", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_reconciliation_matches_origine"),
        "reconciliation_matches",
        "origine IN ('Automatique', 'Manuelle', 'Frais')",
    )

    op.execute(
        sa.text(
            "INSERT INTO permissions (code, description) VALUES (:code, :description) "
            "ON CONFLICT (code) DO NOTHING"
        ).bindparams(code=PERMISSION, description=DESCRIPTION)
    )
    op.execute(
        sa.text(
            "INSERT INTO role_permissions (role_id, permission_id) "
            "SELECT r.id, p.id FROM roles r, permissions p "
            "WHERE r.code IN ('ADMIN', 'COMPTABLE') AND p.code = :code "
            "ON CONFLICT DO NOTHING"
        ).bindparams(code=PERMISSION)
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM permissions WHERE code = :code").bindparams(code=PERMISSION))
    op.execute("UPDATE reconciliation_matches SET origine = 'Manuelle' WHERE origine = 'Frais'")
    op.drop_constraint(
        op.f("ck_reconciliation_matches_origine"), "reconciliation_matches", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_reconciliation_matches_origine"),
        "reconciliation_matches",
        "origine IN ('Automatique', 'Manuelle')",
    )
    op.drop_index("ix_accounting_entries_simtis", table_name="accounting_entries")
    op.drop_constraint(
        op.f("ck_accounting_entries_export_simtis"), "accounting_entries", type_="check"
    )
    op.drop_constraint(op.f("ck_accounting_entries_origine"), "accounting_entries", type_="check")
    op.drop_column("accounting_entries", "exportee_le")
    op.drop_column("accounting_entries", "origine")
    op.drop_column("bank_accounts", "compte_timbre")
    op.drop_column("bank_accounts", "journal_frais")
