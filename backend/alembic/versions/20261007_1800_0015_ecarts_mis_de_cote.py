"""ecarts mis de cote

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-07 18:00:00

Données seulement. Décision du 07/10/2026 : la fonction Écarts (P12) est mise de côté pour le moment
(masquée à l'écran par `ECARTS_ACTIFS` dans `frontend/lib/features.ts`). Les écarts encore ouverts
sont clôturés, comme une clôture faite à l'écran : commentaire, auteur, date, trace d'audit
`cloture_ecart`. Leurs lignes encore au statut « Écart » redeviennent « Non rapprochée ».

L'auteur de la clôture (obligatoire en base) est le premier administrateur actif. S'il y a des
écarts ouverts mais aucun administrateur, la migration s'arrête plutôt que d'inventer un auteur.
Le downgrade ne rouvre rien : une clôture est définitive.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MOTIF = "Fonction Écarts mise de côté le 07/10/2026."


def upgrade() -> None:
    connection = op.get_bind()
    ouverts = connection.execute(
        sa.text("SELECT count(*) FROM discrepancies WHERE statut <> 'Clôturé'")
    ).scalar_one()
    if not ouverts:
        return
    admin_id = connection.execute(
        sa.text(
            """
            SELECT u.id FROM users u
            JOIN user_roles ur ON ur.user_id = u.id
            JOIN roles r ON r.id = ur.role_id
            WHERE r.code = 'ADMIN' AND u.actif
            ORDER BY u.id
            LIMIT 1
            """
        )
    ).scalar()
    if admin_id is None:
        raise RuntimeError(
            f"{ouverts} écart(s) ouvert(s) à clôturer, mais aucun administrateur actif pour en être "
            "l'auteur : créez un administrateur (python -m app.cli create-user --role ADMIN), "
            "puis relancez la migration."
        )
    params = {"admin": admin_id, "motif": MOTIF}

    # 1. Les lignes encore « Écart » à cause d'un écart ouvert redeviennent « Non rapprochée »
    connection.execute(
        sa.text(
            """
            UPDATE bank_transactions SET statut = 'Non rapprochée', updated_at = now()
            WHERE statut = 'Écart' AND id IN (
                SELECT bank_transaction_id FROM discrepancies
                WHERE statut <> 'Clôturé' AND bank_transaction_id IS NOT NULL
            )
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE accounting_entries SET statut = 'Non rapprochée', updated_at = now()
            WHERE statut = 'Écart' AND id IN (
                SELECT accounting_entry_id FROM discrepancies
                WHERE statut <> 'Clôturé' AND accounting_entry_id IS NOT NULL
            )
            """
        )
    )

    # 2. Une trace d'audit par écart, avec l'état avant et après
    connection.execute(
        sa.text(
            """
            INSERT INTO audit_logs (user_id, action, entite, entite_id, ancienne_valeur,
                                    nouvelle_valeur)
            SELECT :admin, 'cloture_ecart', 'discrepancy', d.id::text,
                   jsonb_build_object('statut', d.statut, 'commentaire', d.commentaire),
                   jsonb_build_object(
                       'statut', 'Clôturé',
                       'commentaire', concat_ws(' ', nullif(btrim(d.commentaire), ''), CAST(:motif AS text)),
                       'origine', 'Migration 0015'
                   )
            FROM discrepancies d
            WHERE d.statut <> 'Clôturé'
            """
        ),
        params,
    )

    # 3. La clôture elle-même : commentaire (ajouté à l'existant), auteur, date
    connection.execute(
        sa.text(
            """
            UPDATE discrepancies
            SET statut = 'Clôturé',
                commentaire = concat_ws(' ', nullif(btrim(commentaire), ''), CAST(:motif AS text)),
                cloture_le = now(),
                cloture_par_id = :admin,
                traite_le = coalesce(traite_le, now()),
                updated_at = now()
            WHERE statut <> 'Clôturé'
            """
        ),
        params,
    )


def downgrade() -> None:
    # Une clôture est définitive : rien n'est rouvert
    pass
