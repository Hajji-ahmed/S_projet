"""plusieurs journaux sage

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-12 12:00:00

Décision du 12/10/2026 : un compte bancaire peut avoir plusieurs journaux Sage (BP : 5243 pour les
encaissements, 5543 pour les frais, commissions et remboursements). `bank_accounts.journal_sage`
garde une liste séparée par des virgules (« 5243,5543 »). L'index d'unicité (un journal par compte
actif et par société) ne sait pas comparer deux listes : il est remplacé par un déclencheur qui
refuse qu'un journal soit déjà celui d'un autre compte actif de la même société.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FONCTION = """
CREATE FUNCTION bank_accounts_journaux_uniques() RETURNS trigger AS $$
DECLARE
    autre RECORD;
BEGIN
    IF NEW.actif AND NEW.journal_sage IS NOT NULL THEN
        SELECT a.id INTO autre FROM bank_accounts a
        WHERE a.company_id = NEW.company_id AND a.actif AND a.id <> NEW.id
          AND a.journal_sage IS NOT NULL
          AND string_to_array(a.journal_sage, ',') && string_to_array(NEW.journal_sage, ',')
        LIMIT 1;
        IF FOUND THEN
            RAISE EXCEPTION 'Journal Sage deja utilise par le compte % de la societe', autre.id
                USING ERRCODE = 'unique_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.drop_index("uq_bank_accounts_journal_sage_actif", table_name="bank_accounts")
    op.alter_column(
        "bank_accounts",
        "journal_sage",
        type_=sa.String(length=120),
        existing_type=sa.String(length=10),
        existing_nullable=True,
    )
    op.execute(FONCTION)
    op.execute(
        "CREATE TRIGGER bank_accounts_journaux_uniques BEFORE INSERT OR UPDATE ON bank_accounts "
        "FOR EACH ROW EXECUTE FUNCTION bank_accounts_journaux_uniques()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER bank_accounts_journaux_uniques ON bank_accounts")
    op.execute("DROP FUNCTION bank_accounts_journaux_uniques()")
    # Un compte à plusieurs journaux garde le premier
    op.execute(
        "UPDATE bank_accounts SET journal_sage = split_part(journal_sage, ',', 1) "
        "WHERE journal_sage LIKE '%,%'"
    )
    op.alter_column(
        "bank_accounts",
        "journal_sage",
        type_=sa.String(length=10),
        existing_type=sa.String(length=120),
        existing_nullable=True,
    )
    op.create_index(
        "uq_bank_accounts_journal_sage_actif",
        "bank_accounts",
        ["company_id", "journal_sage"],
        unique=True,
        postgresql_where=sa.text("journal_sage IS NOT NULL AND actif"),
    )
