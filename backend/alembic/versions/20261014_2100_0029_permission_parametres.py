"""permission admin.settings

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-14 21:00:00

Phase P16.3 (14/10/2026) : la grille de rapprochement et les modèles de mapping d'import se
modifient à l'écran Administration > Paramètres, avec la permission `admin.settings`, donnée au rôle
Administrateur existant (les seeds n'appliquent les permissions qu'à la création d'un rôle).
Données seulement : aucune table ne change.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSION = "admin.settings"
DESCRIPTION = "Modifier les paramètres (grille de rapprochement, modèles d'import)"


def upgrade() -> None:
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
            "WHERE r.code = 'ADMIN' AND p.code = :code "
            "ON CONFLICT DO NOTHING"
        ).bindparams(code=PERMISSION)
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM permissions WHERE code = :code").bindparams(code=PERMISSION))
