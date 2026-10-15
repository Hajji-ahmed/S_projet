"""numero de piece des ecritures de frais

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-15 10:00:00

Décision du 15/10/2026 : le N° pièce d'une écriture de frais créée par SIMTIS s'écrit AAMMNNN
(année et mois de la date d'écriture, puis un n° d'ordre du mois sur 3 chiffres, ex. 2610018), un
compteur par société et par mois (`frais_piece_counters`, sans trou). Le code de rapprochement, qui
servait de N° pièce, part dans la colonne « Référence » de l'export Sage.

Données : les écritures de frais pas encore exportées sont renumérotées dans l'ordre de leur date
(puis de leur création), une ligne d'audit `renumerotation_piece` chacune ; celles déjà exportées
gardent leur ancien n° (Sage les connaît sous ce n°). Le downgrade supprime la table mais ne rend
pas les anciens n° (ils restent dans l'audit).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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
    op.execute(
        """
        CREATE TEMP TABLE renumerotees ON COMMIT DROP AS
        SELECT id, company_id, numero_piece AS ancien,
               EXTRACT(YEAR FROM date_ecriture)::int AS annee,
               EXTRACT(MONTH FROM date_ecriture)::int AS mois,
               to_char(date_ecriture, 'YYMM') || lpad(row_number() OVER (
                   PARTITION BY company_id, date_trunc('month', date_ecriture)
                   ORDER BY date_ecriture, id)::text, 3, '0') AS nouveau
        FROM accounting_entries
        WHERE origine = 'SIMTIS' AND exportee_le IS NULL
        """
    )
    op.execute(
        """
        INSERT INTO audit_logs (user_id, action, entite, entite_id, ancienne_valeur, nouvelle_valeur)
        SELECT NULL, 'renumerotation_piece', 'accounting_entry', id::text,
               jsonb_build_object('numero_piece', ancien),
               jsonb_build_object('numero_piece', nouveau, 'origine', 'Migration 0030')
        FROM renumerotees ORDER BY id
        """
    )
    op.execute(
        "UPDATE accounting_entries e SET numero_piece = r.nouveau "
        "FROM renumerotees r WHERE e.id = r.id"
    )
    op.execute(
        "INSERT INTO frais_piece_counters (company_id, annee, mois, dernier) "
        "SELECT company_id, annee, mois, count(*) FROM renumerotees GROUP BY 1, 2, 3"
    )


def downgrade() -> None:
    op.drop_table("frais_piece_counters")
