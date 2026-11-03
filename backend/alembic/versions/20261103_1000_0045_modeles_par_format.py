"""column_mappings : un modèle de relevé par format de fichier

Revision ID: 0045
Revises: 0044
Create Date: 2026-11-03 10:00:00

Décision du 03/11/2026 : une banque garde un modèle de colonnes par sorte de fichier, Excel
(.xlsx et .xls) ou PDF, et à part pour le fichier des opérations en cours ; importer un PDF
n'écrase plus le modèle Excel. Le modèle Sage d'une société n'a pas de format.

Chaque modèle de relevé existant prend le format et la sorte du dernier relevé confirmé de sa
banque (Excel, relevé normal faute d'import). Le retour arrière garde le plus récent par banque.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0045"
down_revision: str | None = "0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Nom d'un modèle de relevé, comme `import_service.nom_modele`
NOM = (
    "CASE WHEN m.en_cours THEN 'Opérations en cours ' ELSE 'Relevé ' END "
    "|| b.code || ' · ' || m.format_fichier"
)


def upgrade() -> None:
    op.add_column("column_mappings", sa.Column("format_fichier", sa.String(5), nullable=True))
    op.add_column(
        "column_mappings",
        sa.Column("en_cours", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    # Un seul modèle par banque jusqu'ici (le plus récent servait) : les plus anciens partent
    op.execute(
        """
        DELETE FROM column_mappings m
        USING column_mappings r
        WHERE m.bank_id IS NOT NULL AND r.bank_id = m.bank_id AND r.type = m.type
          AND (r.updated_at, r.id) > (m.updated_at, m.id)
        """
    )
    # Format et sorte du dernier relevé confirmé de la banque
    op.execute(
        """
        UPDATE column_mappings m
        SET format_fichier = COALESCE(dernier.format_fichier, 'Excel'),
            en_cours = COALESCE(dernier.en_cours, false)
        FROM (
            SELECT bm.id AS mapping_id,
                   (SELECT CASE WHEN lower(ib.fichier_nom) LIKE '%.pdf' THEN 'PDF' ELSE 'Excel' END
                    FROM import_batches ib
                    JOIN bank_statements s ON s.import_batch_id = ib.id
                    JOIN bank_accounts a ON a.id = s.bank_account_id
                    WHERE a.bank_id = bm.bank_id AND ib.statut = 'Confirmé'
                    ORDER BY ib.id DESC LIMIT 1) AS format_fichier,
                   (SELECT s.en_cours
                    FROM import_batches ib
                    JOIN bank_statements s ON s.import_batch_id = ib.id
                    JOIN bank_accounts a ON a.id = s.bank_account_id
                    WHERE a.bank_id = bm.bank_id AND ib.statut = 'Confirmé'
                    ORDER BY ib.id DESC LIMIT 1) AS en_cours
            FROM column_mappings bm
            WHERE bm.bank_id IS NOT NULL
        ) AS dernier
        WHERE m.id = dernier.mapping_id
        """
    )
    op.execute(f"UPDATE column_mappings m SET nom = {NOM} FROM banks b WHERE b.id = m.bank_id")
    # L'autogénération ne voit pas les CHECK (tests dans test_constraints.py)
    op.create_check_constraint(
        op.f("ck_column_mappings_format_fichier"),
        "column_mappings",
        "format_fichier IN ('Excel', 'PDF')",
    )
    op.create_check_constraint(
        op.f("ck_column_mappings_format_si_banque"),
        "column_mappings",
        "(bank_id IS NULL) = (format_fichier IS NULL)",
    )
    op.create_index(
        "uq_column_mappings_banque_format",
        "column_mappings",
        ["bank_id", "type", "format_fichier", "en_cours"],
        unique=True,
        postgresql_where=sa.text("bank_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_column_mappings_banque_format", table_name="column_mappings")
    op.drop_constraint(
        op.f("ck_column_mappings_format_si_banque"), "column_mappings", type_="check"
    )
    op.drop_constraint(op.f("ck_column_mappings_format_fichier"), "column_mappings", type_="check")
    op.execute(
        """
        DELETE FROM column_mappings m
        USING column_mappings r
        WHERE m.bank_id IS NOT NULL AND r.bank_id = m.bank_id AND r.type = m.type
          AND (r.updated_at, r.id) > (m.updated_at, m.id)
        """
    )
    op.execute(
        "UPDATE column_mappings m SET nom = 'Relevé ' || b.code FROM banks b WHERE b.id = m.bank_id"
    )
    op.drop_column("column_mappings", "en_cours")
    op.drop_column("column_mappings", "format_fichier")
