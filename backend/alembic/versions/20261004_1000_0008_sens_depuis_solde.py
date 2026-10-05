"""sens des operations deduit du solde

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-04 10:00:00

Migration de données seulement (aucun changement de schéma). Le relevé BP
« Releve_bancaire_SIMTIS_Septembre_Format_Different.xlsx » avait une colonne Montant toujours
positive : toutes ses opérations ont été enregistrées au crédit. Décision du 04/10/2026 : le sens se
déduit du Solde (règle `import_service._direction_from_balances` pour les prochains imports).

Pour chaque relevé, la chaîne des soldes est suivie depuis son solde d'ouverture ; une opération au
crédit passe au débit seulement si la chaîne le PROUVE (solde précédent − montant = solde, et pas
solde précédent + montant = solde). Pour ces opérations : débit, crédit, montant signé, Pointage
automatique « Encaissement » → « Décaissement », et empreinte de ligne recalculée (si l'ancienne se
reproduit) pour qu'un nouvel import du fichier reconnaisse les lignes. Un contrôle de solde
« À vérifier » dont les mouvements retrouvent maintenant le solde de clôture devient « Conforme » ou
« Écart ». Une ligne d'audit `correction_sens` résume la correction. Le retour arrière ne défait rien.
"""

import hashlib
import json
from collections import defaultdict
from collections.abc import Sequence
from decimal import Decimal

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ZERO = Decimal("0.00")


def _hash(account_id: int, parts: tuple, occurrence: int) -> str:
    """Copie figée de `normalization_service.line_hash` (une migration ne dépend pas du code)."""
    values = (account_id, *parts, occurrence)
    return hashlib.sha256(
        "|".join("" if part is None else str(part) for part in values).encode()
    ).hexdigest()


def _key(row, debit: Decimal, credit: Decimal) -> tuple:
    return (
        row.date_operation,
        row.date_valeur,
        row.libelle,
        debit,
        credit,
        row.solde,
        row.reference,
    )


def _with_occurrences(rows, keys) -> list[int]:
    seen: dict[tuple, int] = defaultdict(int)
    occurrences = []
    for key in keys:
        seen[key] += 1
        occurrences.append(seen[key])
    return occurrences


def upgrade() -> None:
    connection = op.get_bind()
    codes = dict(connection.execute(text("SELECT code, id FROM pointage_types")).all())
    encaissement, decaissement = codes.get("ENCAISSEMENT"), codes.get("DECAISSEMENT")

    statements = connection.execute(
        text("SELECT id, bank_account_id, solde_ouverture, solde_cloture FROM bank_statements")
    ).all()
    fixed_ops: list[int] = []
    fixed_statements: list[int] = []
    for statement in statements:
        rows = connection.execute(
            text(
                "SELECT id, date_operation, date_valeur, libelle, debit, credit, montant, solde, "
                "reference, hash_ligne, pointage_type_id FROM bank_transactions "
                "WHERE statement_id = :id ORDER BY id"
            ),
            {"id": statement.id},
        ).all()
        if not rows or any(row.debit for row in rows):
            continue  # relevé déjà avec des débits : sa colonne de montant avait un sens
        # Ordre chronologique, comme à l'import (un fichier peut aller du plus récent au plus ancien)
        ordered = rows[::-1] if rows[0].date_operation > rows[-1].date_operation else rows

        previous = statement.solde_ouverture
        debits = set()
        for row in ordered:
            if row.credit and previous is not None and row.solde is not None:
                if previous + row.credit != row.solde and previous - row.credit == row.solde:
                    debits.add(row.id)
            previous = row.solde
        if not debits:
            continue

        # Empreintes : l'ancienne doit se reproduire, sinon on ne la touche pas
        old_keys = [_key(row, row.debit, row.credit) for row in rows]
        new_keys = [
            _key(row, row.credit, ZERO) if row.id in debits else _key(row, row.debit, row.credit)
            for row in rows
        ]
        old_occ = _with_occurrences(rows, old_keys)
        new_occ = _with_occurrences(rows, new_keys)
        for row, old_key, old_n, new_key, new_n in zip(
            rows, old_keys, old_occ, new_keys, new_occ, strict=True
        ):
            if row.id not in debits:
                continue
            same_formula = _hash(statement.bank_account_id, old_key, old_n) == row.hash_ligne
            pointage = row.pointage_type_id
            if pointage is not None and pointage == encaissement and decaissement is not None:
                pointage = decaissement
            connection.execute(
                text(
                    "UPDATE bank_transactions SET debit = :debit, credit = 0, montant = :montant, "
                    "pointage_type_id = :pointage, hash_ligne = :hash, updated_at = now() "
                    "WHERE id = :id"
                ),
                {
                    "id": row.id,
                    "debit": row.credit,
                    "montant": -row.credit,
                    "pointage": pointage,
                    "hash": _hash(statement.bank_account_id, new_key, new_n)
                    if same_formula
                    else row.hash_ligne,
                },
            )
            fixed_ops.append(row.id)
        fixed_statements.append(statement.id)

        # Contrôle du solde : les mouvements retrouvent-ils maintenant le solde de clôture ?
        movements = connection.execute(
            text(
                "SELECT coalesce(sum(montant), 0) FROM bank_transactions WHERE statement_id = :id"
            ),
            {"id": statement.id},
        ).scalar_one()
        if (
            statement.solde_ouverture is not None
            and statement.solde_cloture is not None
            and statement.solde_ouverture + movements == statement.solde_cloture
        ):
            connection.execute(
                text(
                    "UPDATE balance_checks SET commentaire = NULL, updated_at = now(), "
                    "statut = CASE WHEN ecart = 0 THEN 'Conforme' ELSE 'Écart' END "
                    "WHERE bank_statement_id = :id AND statut = 'À vérifier'"
                ),
                {"id": statement.id},
            )

    if fixed_ops:
        connection.execute(
            text(
                "INSERT INTO audit_logs (user_id, action, entite, nouvelle_valeur) "
                "VALUES (NULL, 'correction_sens', 'bank_transaction', CAST(:valeur AS jsonb))"
            ),
            {
                "valeur": json.dumps(
                    {
                        "migration": "0008",
                        "operations": sorted(fixed_ops),
                        "releves": sorted(fixed_statements),
                    }
                )
            },
        )


def downgrade() -> None:
    # Rien à défaire : le sens corrigé est celui que prouve le solde du relevé.
    pass
