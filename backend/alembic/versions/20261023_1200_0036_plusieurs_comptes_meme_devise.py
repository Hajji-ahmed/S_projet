"""plusieurs comptes par banque et devise

Revision ID: 0036
Revises: 0035
Create Date: 2026-10-23 12:00:00

Décision du 23/10/2026 : une société peut avoir plusieurs comptes actifs dans la même banque et la
même devise (par exemple deux comptes BMCE en USD). L'index unique partiel
`uq_bank_accounts_compte_actif_par_banque` (migration 0003) est supprimé ; les tableaux Banques et
Devises font la somme des comptes d'une banque (même devise). Le numéro reste unique, et un journal
Sage ne sert toujours qu'à un compte actif.

Les codes de rapprochement « BANQUE-AA-NNNNNN » sont uniques par société, mais leur compteur était
tenu par compte : deux comptes de la même banque (BMCE MAD et BMCE USD) auraient donné le même code.
Le compteur passe à (société, banque, année), repris au plus grand numéro déjà donné : aucun code
existant ne change ni ne sera réutilisé.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("uq_bank_accounts_compte_actif_par_banque", table_name="bank_accounts")

    op.create_table(
        "reconciliation_code_counters_banque",
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("bank_id", sa.Integer(), nullable=False),
        sa.Column("annee", sa.Integer(), nullable=False),
        sa.Column("dernier", sa.Integer(), nullable=False),
    )
    # Plus grand numéro déjà donné, lu dans les codes (y compris ceux des rapprochements annulés) et
    # dans les anciens compteurs par compte
    op.execute(
        """
        INSERT INTO reconciliation_code_counters_banque (company_id, bank_id, annee, dernier)
        SELECT company_id, bank_id, annee, max(dernier)
        FROM (
            SELECT m.company_id, b.id AS bank_id,
                   2000 + substring(m.code FROM '-([0-9]{2})-[0-9]+$')::int AS annee,
                   substring(m.code FROM '-([0-9]+)$')::int AS dernier
            FROM reconciliation_matches m
            JOIN banks b ON b.code = substring(m.code FROM '^(.+)-[0-9]{2}-[0-9]+$')
            WHERE m.code ~ '^.+-[0-9]{2}-[0-9]+$'
            UNION ALL
            SELECT a.company_id, a.bank_id, c.annee, c.dernier
            FROM reconciliation_code_counters c
            JOIN bank_accounts a ON a.id = c.bank_account_id
        ) AS numeros
        GROUP BY company_id, bank_id, annee
        """
    )
    op.drop_table("reconciliation_code_counters")
    op.rename_table("reconciliation_code_counters_banque", "reconciliation_code_counters")
    op.create_primary_key(
        "pk_reconciliation_code_counters",
        "reconciliation_code_counters",
        ["company_id", "bank_id", "annee"],
    )
    op.create_foreign_key(
        "fk_reconciliation_code_counters_company_id_companies",
        "reconciliation_code_counters",
        "companies",
        ["company_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_reconciliation_code_counters_bank_id_banks",
        "reconciliation_code_counters",
        "banks",
        ["bank_id"],
        ["id"],
    )


def downgrade() -> None:
    # Le retour au compteur par compte n'est possible que si la règle « un compte actif par banque,
    # devise et type » est de nouveau respectée ; les compteurs sont recalculés depuis les codes
    op.create_table(
        "reconciliation_code_counters_compte",
        sa.Column("bank_account_id", sa.Integer(), nullable=False),
        sa.Column("annee", sa.Integer(), nullable=False),
        sa.Column("dernier", sa.Integer(), nullable=False),
    )
    op.execute(
        """
        INSERT INTO reconciliation_code_counters_compte (bank_account_id, annee, dernier)
        SELECT a.id, c.annee, c.dernier
        FROM reconciliation_code_counters c
        JOIN bank_accounts a ON a.company_id = c.company_id AND a.bank_id = c.bank_id
        """
    )
    op.drop_table("reconciliation_code_counters")
    op.rename_table("reconciliation_code_counters_compte", "reconciliation_code_counters")
    op.create_primary_key(
        "pk_reconciliation_code_counters",
        "reconciliation_code_counters",
        ["bank_account_id", "annee"],
    )
    op.create_foreign_key(
        "fk_reconciliation_code_counters_bank_account_id_bank_accounts",
        "reconciliation_code_counters",
        "bank_accounts",
        ["bank_account_id"],
        ["id"],
    )
    op.create_index(
        "uq_bank_accounts_compte_actif_par_banque",
        "bank_accounts",
        ["company_id", "bank_id", "devise", "type_compte"],
        unique=True,
        postgresql_where=sa.text("actif"),
    )
