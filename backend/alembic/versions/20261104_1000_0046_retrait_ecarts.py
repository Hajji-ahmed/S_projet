"""retrait de la fonction Écarts

Revision ID: 0046
Revises: 0045
Create Date: 2026-11-04 10:00:00

Décision du 04/11/2026 : la fonction Écarts (P12), mise de côté le 07/10/2026 (migration 0015),
est retirée du code. La table `discrepancies` part avec ses écarts, tous clôturés (leur trace reste
dans `audit_logs`), ainsi que la permission `discrepancies.manage` (ses liens aux rôles et aux
personnes partent en cascade) et le statut de rapprochement « Écart » des opérations et des
écritures.

La migration s'arrête s'il reste un écart ouvert ou une ligne au statut « Écart » : ils se
traitent avant, rien n'est changé en silence. Le retour arrière recrée la table vide, la
permission sans rôle et l'ancien CHECK.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0046"
down_revision: str | None = "0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSION = "discrepancies.manage"
DESCRIPTION = "Traiter et clôturer les écarts"
STATUTS = "statut IN ('Non rapprochée', 'À vérifier', 'Rapprochée')"
STATUTS_AVEC_ECART = "statut IN ('Non rapprochée', 'À vérifier', 'Rapprochée', 'Écart')"
TABLES_LIGNES = ("bank_transactions", "accounting_entries")


def upgrade() -> None:
    connection = op.get_bind()
    ouverts = connection.execute(
        sa.text("SELECT count(*) FROM discrepancies WHERE statut <> 'Clôturé'")
    ).scalar_one()
    en_ecart = sum(
        connection.execute(
            sa.text(f"SELECT count(*) FROM {table} WHERE statut = 'Écart'")
        ).scalar_one()
        for table in TABLES_LIGNES
    )
    if ouverts or en_ecart:
        raise RuntimeError(
            f"{ouverts} écart(s) ouvert(s) et {en_ecart} ligne(s) au statut « Écart » : "
            "remettez-les en « Non rapprochée » avant de retirer la fonction Écarts."
        )

    op.drop_table("discrepancies")
    op.execute(sa.text("DELETE FROM permissions WHERE code = :code").bindparams(code=PERMISSION))
    # L'autogénération ne voit pas les CHECK : test dans test_constraints.py
    for table in TABLES_LIGNES:
        op.drop_constraint(op.f(f"ck_{table}_statut"), table, type_="check")
        op.create_check_constraint(op.f(f"ck_{table}_statut"), table, STATUTS)


def downgrade() -> None:
    for table in TABLES_LIGNES:
        op.drop_constraint(op.f(f"ck_{table}_statut"), table, type_="check")
        op.create_check_constraint(op.f(f"ck_{table}_statut"), table, STATUTS_AVEC_ECART)
    op.execute(
        sa.text(
            "INSERT INTO permissions (code, description) VALUES (:code, :description) "
            "ON CONFLICT (code) DO NOTHING"
        ).bindparams(code=PERMISSION, description=DESCRIPTION)
    )
    # Table de la migration 0001, avec les index d'un seul écart ouvert de la migration 0012
    op.create_table(
        "discrepancies",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("bank_transaction_id", sa.Integer(), nullable=True),
        sa.Column("accounting_entry_id", sa.Integer(), nullable=True),
        sa.Column("montant", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("difference", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("date_ecart", sa.Date(), nullable=False),
        sa.Column("responsable_id", sa.Integer(), nullable=True),
        sa.Column("statut", sa.String(length=10), server_default="À traiter", nullable=False),
        sa.Column("commentaire", sa.Text(), nullable=True),
        sa.Column("traite_le", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cloture_le", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cloture_par_id", sa.Integer(), nullable=True),
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
            "statut <> 'Clôturé' OR (commentaire IS NOT NULL AND btrim(commentaire) <> '' "
            "AND cloture_le IS NOT NULL AND cloture_par_id IS NOT NULL)",
            name=op.f("ck_discrepancies_cloture_avec_commentaire"),
        ),
        sa.CheckConstraint(
            "statut IN ('À traiter', 'En cours', 'Traité', 'Clôturé')",
            name=op.f("ck_discrepancies_statut"),
        ),
        sa.CheckConstraint(
            "type IN ('Banque sans écriture', 'Écriture sans banque', 'Montant différent', "
            "'Date différente', 'Libellé ambigu', 'Doublon potentiel')",
            name=op.f("ck_discrepancies_type"),
        ),
        sa.ForeignKeyConstraint(
            ["accounting_entry_id"],
            ["accounting_entries.id"],
            name=op.f("fk_discrepancies_accounting_entry_id_accounting_entries"),
        ),
        sa.ForeignKeyConstraint(
            ["bank_transaction_id"],
            ["bank_transactions.id"],
            name=op.f("fk_discrepancies_bank_transaction_id_bank_transactions"),
        ),
        sa.ForeignKeyConstraint(
            ["cloture_par_id"], ["users.id"], name=op.f("fk_discrepancies_cloture_par_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name=op.f("fk_discrepancies_company_id_companies")
        ),
        sa.ForeignKeyConstraint(
            ["responsable_id"], ["users.id"], name=op.f("fk_discrepancies_responsable_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discrepancies")),
    )
    for colonne in ("accounting_entry_id", "bank_transaction_id", "company_id", "statut"):
        op.create_index(op.f(f"ix_discrepancies_{colonne}"), "discrepancies", [colonne])
    op.create_index(
        "uq_discrepancies_transaction_ouvert",
        "discrepancies",
        ["bank_transaction_id"],
        unique=True,
        postgresql_where=sa.text("statut <> 'Clôturé' AND bank_transaction_id IS NOT NULL"),
    )
    op.create_index(
        "uq_discrepancies_ecriture_ouvert",
        "discrepancies",
        ["accounting_entry_id"],
        unique=True,
        postgresql_where=sa.text("statut <> 'Clôturé' AND accounting_entry_id IS NOT NULL"),
    )
