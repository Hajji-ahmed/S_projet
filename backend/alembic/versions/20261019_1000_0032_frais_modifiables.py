"""propositions de frais modifiables et ecartees

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-19 10:00:00

Décision du 19/10/2026 : avant de valider une proposition de frais, l'utilisateur peut modifier son
libellé et sa date, et ses lignes (compte, libellé, montant ; le total reste la somme des
opérations) ; il peut aussi écarter une journée (ses frais passent dans « Autres frais »).

- `frais_lignes` : lignes saisies d'une écriture SIMTIS (supprimées avec elle) ;
- `frais_jours_ecartes` : une journée (compte, jour, famille) écartée.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "frais_lignes",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("accounting_entry_id", sa.Integer(), nullable=False),
        sa.Column("ordre", sa.Integer(), nullable=False),
        sa.Column("compte", sa.String(length=20), nullable=False),
        sa.Column("libelle", sa.String(length=60), nullable=False),
        sa.Column("montant", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("sens", sa.String(length=10), nullable=False),
        sa.CheckConstraint("montant > 0", name=op.f("ck_frais_lignes_montant_positif")),
        sa.CheckConstraint("sens IN ('Crédit', 'Débit')", name=op.f("ck_frais_lignes_sens_valide")),
        sa.ForeignKeyConstraint(
            ["accounting_entry_id"],
            ["accounting_entries.id"],
            name=op.f("fk_frais_lignes_accounting_entry_id_accounting_entries"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_frais_lignes")),
        sa.UniqueConstraint("accounting_entry_id", "ordre", name="uq_frais_lignes_ecriture_ordre"),
    )
    op.create_index(
        op.f("ix_frais_lignes_accounting_entry_id"),
        "frais_lignes",
        ["accounting_entry_id"],
        unique=False,
    )
    op.create_table(
        "frais_jours_ecartes",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("bank_account_id", sa.Integer(), nullable=False),
        sa.Column("jour", sa.Date(), nullable=False),
        sa.Column("famille", sa.String(length=20), nullable=False),
        sa.Column("motif", sa.String(length=500), nullable=True),
        sa.Column("cree_par_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "famille IN ('timbres', 'commissions', 'frais')",
            name=op.f("ck_frais_jours_ecartes_famille_valide"),
        ),
        sa.ForeignKeyConstraint(
            ["bank_account_id"],
            ["bank_accounts.id"],
            name=op.f("fk_frais_jours_ecartes_bank_account_id_bank_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_frais_jours_ecartes_company_id_companies"),
        ),
        sa.ForeignKeyConstraint(
            ["cree_par_id"], ["users.id"], name=op.f("fk_frais_jours_ecartes_cree_par_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_frais_jours_ecartes")),
        sa.UniqueConstraint(
            "bank_account_id", "jour", "famille", name="uq_frais_jours_ecartes_compte_jour_famille"
        ),
    )
    op.create_index(
        op.f("ix_frais_jours_ecartes_company_id"),
        "frais_jours_ecartes",
        ["company_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_frais_jours_ecartes_company_id"), table_name="frais_jours_ecartes")
    op.drop_table("frais_jours_ecartes")
    op.drop_index(op.f("ix_frais_lignes_accounting_entry_id"), table_name="frais_lignes")
    op.drop_table("frais_lignes")
