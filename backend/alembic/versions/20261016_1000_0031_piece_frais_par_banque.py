"""numero de piece des frais par banque

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-16 10:00:00

Décision du 16/10/2026 : le N° pièce d'une écriture de frais créée par SIMTIS s'écrit BANQUE AAMMNNN
(code de la banque, année et mois de la date d'écriture, puis un n° d'ordre du mois sur 3 chiffres,
ex. BP2610123), un compteur par société, banque et mois (`frais_piece_counters.bank_id`).

Données : les écritures de frais pas encore exportées sont renumérotées dans l'ordre de leur date
(puis de leur création), une ligne d'audit `renumerotation_piece` chacune ; celles déjà exportées
gardent leur ancien n° (Sage les connaît sous ce n°). Le downgrade remet le compteur par société et
par mois mais ne rend pas les anciens n° (ils restent dans l'audit).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("frais_piece_counters")
    op.create_table(
        "frais_piece_counters",
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("bank_id", sa.Integer(), nullable=False),
        sa.Column("annee", sa.Integer(), nullable=False),
        sa.Column("mois", sa.Integer(), nullable=False),
        sa.Column("dernier", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_frais_piece_counters_company_id_companies"),
        ),
        sa.ForeignKeyConstraint(
            ["bank_id"], ["banks.id"], name=op.f("fk_frais_piece_counters_bank_id_banks")
        ),
        sa.PrimaryKeyConstraint(
            "company_id", "bank_id", "annee", "mois", name=op.f("pk_frais_piece_counters")
        ),
    )
    op.execute(
        """
        CREATE TEMP TABLE pieces_par_banque ON COMMIT DROP AS
        SELECT e.id, e.company_id, a.bank_id, e.numero_piece AS ancien,
               EXTRACT(YEAR FROM e.date_ecriture)::int AS annee,
               EXTRACT(MONTH FROM e.date_ecriture)::int AS mois,
               b.code || to_char(e.date_ecriture, 'YYMM') || lpad(row_number() OVER (
                   PARTITION BY e.company_id, a.bank_id, date_trunc('month', e.date_ecriture)
                   ORDER BY e.date_ecriture, e.id)::text, 3, '0') AS nouveau
        FROM accounting_entries e
        JOIN bank_accounts a ON a.id = e.bank_account_id
        JOIN banks b ON b.id = a.bank_id
        WHERE e.origine = 'SIMTIS' AND e.exportee_le IS NULL
        """
    )
    op.execute(
        """
        INSERT INTO audit_logs (user_id, action, entite, entite_id, ancienne_valeur, nouvelle_valeur)
        SELECT NULL, 'renumerotation_piece', 'accounting_entry', id::text,
               jsonb_build_object('numero_piece', ancien),
               jsonb_build_object('numero_piece', nouveau, 'origine', 'Migration 0031')
        FROM pieces_par_banque ORDER BY id
        """
    )
    op.execute(
        "UPDATE accounting_entries e SET numero_piece = r.nouveau "
        "FROM pieces_par_banque r WHERE e.id = r.id"
    )
    op.execute(
        "INSERT INTO frais_piece_counters (company_id, bank_id, annee, mois, dernier) "
        "SELECT company_id, bank_id, annee, mois, count(*) FROM pieces_par_banque GROUP BY 1, 2, 3, 4"
    )
    op.execute("DROP TABLE pieces_par_banque")


def downgrade() -> None:
    op.drop_table("frais_piece_counters")
    op.create_table(
        "frais_piece_counters",
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("annee", sa.Integer(), nullable=False),
        sa.Column("mois", sa.Integer(), nullable=False),
        sa.Column("dernier", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_frais_piece_counters_company_id_companies"),
        ),
        sa.PrimaryKeyConstraint(
            "company_id", "annee", "mois", name=op.f("pk_frais_piece_counters")
        ),
    )
