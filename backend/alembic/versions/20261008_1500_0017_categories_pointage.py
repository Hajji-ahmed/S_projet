"""categories pointage

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-08 15:00:00

Décision du 08/10/2026 : les pointages sont les 74 catégories du métier. Cette migration
1. allonge `pointage_types.code` (30 → 60 caractères : codes tirés des libellés) ;
2. crée les 74 catégories (s'il en manque) et désactive les trois types du 02/10/2026
   (Encaissement, Décaissement, Frais bancaires), gardés pour l'historique ;
3. re-pointe les opérations qui portaient un de ces trois types, avec la règle des mots-clés :
   catégorie nommée en mots entiers dans le libellé (la plus longue gagne, quelques synonymes),
   sinon sans pointage. Une trace d'audit `repointage` par opération modifiée.

Le catalogue et la règle sont recopiés ici, figés : une migration ne dépend pas du code qui évolue
(sources : `app/seeds/pointages.py`, `normalization_service.guess_pointage`).
Le downgrade réactive les trois types, sans restaurer les anciens pointages (l'audit les garde).
"""

import json
import re
import unicodedata
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATEGORIES = (
    "A NOUVEAU", "A voir", "AGIOS", "AGIOS D'ECHELLE", "BOURSE", "CARTE MASSARIF",
    "CERTIFICATION CHEQUE", "Cheque de banque", "CHEQUE SOFT", "CHQ ISMAIL KABBAJ", "CHQ ZAI",
    "CLIENT ETRANGER", "CMT 16M", "CMT 25M", "CMT 32M", "CMT 40M", "CMT 70M", "CNSS", "COM",
    "CREDIT OXYGENE", "DGI", "DOUANE", "DROIT", "ENCAISSEMENT CLIENT", "ENCAISSEMENT HORS GROUP",
    "ENCAISSEMENT HORS GROUP/ALLIANCE INDUSTRIELLE", "ENCAISSEMENT HORS GROUP/DECATHLON",
    "ENCAISSEMENT SOFT", "ENCAISSEMENT SOFTTECH", "ESCOMPTE HORS GROUP",
    "ESCOMPTE HORS GROUP+SOFTRETAIL", "ESCOMPTE SOFTRETAIL", "ESCOMPTE SOFTRETAIL+SOFTTECH", "FRAIS",
    "FRAIS D'APPROCHE", "FRAIS RETENUE A LA SOURCE", "FRS LOCAL", "IMP CLIENT", "INTERET",
    "LA PAIE", "LEASE BACK", "MAGASINAGE", "MAROC OUTDOOR", "MISE A DISPOSITION", "MSC",
    "PAIEMENT PAR CARTE", "REDEVANCE", "REFIN", "REFIN EN MAD", "REJET", "REMBOURSEMENT PRÊT",
    "RESTITUTION FRAIS BANCAIRE", "Restitution imp escompte", "RESTITUTION INTERETS DEBITEURS/ACNE",
    "RESTITUTION INTERETS DEBITEURS/FC", "RETENUE A LA SOURCE", "RTGS", "RTGS-Ismail KABBAJ",
    "SIMTIS-SIMTIS", "SIMTIS-SIMTIS+TEFIL-SIMTIS", "SIMTIS-TEFIL", "SPOT", "SRM", "SURESTARIES",
    "TCA", "TEFIL-SIMTIS", "TEFIL-TEFIL", "TVA", "VERSEMENT ISMAIL KABBAJ", "VIGNETTE", "VIR CNSS",
    "VIR ETRANGER", "VIR ISMAIL KABBAJ", "ZAI",
)  # fmt: skip
ANCIENS = ("ENCAISSEMENT", "DECAISSEMENT", "FRAIS_BANCAIRES")
SYNONYMES = {
    "COMMISSION": "COM",
    "COMMISSIONS": "COM",
    "TENUE DE COMPTE": "FRAIS",
    "SALAIRE": "LA PAIE",
    "SALAIRES": "LA PAIE",
    "INTERETS": "INTERET",
    "REMBOURSEMENT PRET": "REMBOURSEMENT PRET",
}
JAMAIS_AUTO = {"A VOIR"}
_NON_ALNUM = re.compile(r"[^A-Z0-9]+")


def _key(text: str | None) -> str:
    raw = unicodedata.normalize("NFKD", text or "")
    plain = "".join(char for char in raw if not unicodedata.combining(char)).upper()
    return " ".join(_NON_ALNUM.sub(" ", plain).split())


def _has(text: str, words: str) -> bool:
    return bool(words) and f" {words} " in f" {text} "


def _guess(libelle: str | None, by_key: dict[str, int]) -> int | None:
    text = _key(libelle)
    if not text:
        return None
    found = [(len(key), key, ident) for key, ident in by_key.items() if _has(text, key)]
    for word, target in SYNONYMES.items():
        if target in by_key and _has(text, _key(word)):
            found.append((len(_key(word)), target, by_key[target]))
    if not found:
        return None
    found.sort(key=lambda item: (-item[0], item[1]))
    return found[0][2]


def upgrade() -> None:
    op.alter_column(
        "pointage_types",
        "code",
        existing_type=sa.String(length=30),
        type_=sa.String(length=60),
        existing_nullable=False,
    )
    connection = op.get_bind()
    # Le compteur d'identifiants peut être en retard sur les lignes (insérées avec leur id)
    connection.execute(
        sa.text(
            "SELECT setval(pg_get_serial_sequence('pointage_types', 'id'), "
            "coalesce(max(id), 0) + 1, false) FROM pointage_types"
        )
    )
    for libelle in CATEGORIES:
        connection.execute(
            sa.text(
                "INSERT INTO pointage_types (code, libelle) VALUES (:code, :libelle) "
                "ON CONFLICT (code) DO NOTHING"
            ),
            {"code": _key(libelle).replace(" ", "_"), "libelle": libelle},
        )
    connection.execute(
        sa.text(
            "UPDATE pointage_types SET actif = false, updated_at = now() WHERE code IN :codes"
        ).bindparams(sa.bindparam("codes", expanding=True)),
        {"codes": list(ANCIENS)},
    )

    types = connection.execute(sa.text("SELECT id, code, libelle, actif FROM pointage_types")).all()
    libelles = {row.id: row.libelle for row in types}
    by_key = {
        _key(row.libelle): row.id
        for row in types
        if row.actif and _key(row.libelle) not in JAMAIS_AUTO
    }
    anciens = {row.id for row in types if row.code in ANCIENS}
    if not anciens:
        return
    operations = connection.execute(
        sa.text(
            "SELECT id, libelle, pointage_type_id FROM bank_transactions "
            "WHERE pointage_type_id IN :ids"
        ).bindparams(sa.bindparam("ids", expanding=True)),
        {"ids": sorted(anciens)},
    ).all()
    for operation in operations:
        nouveau = _guess(operation.libelle, by_key)
        connection.execute(
            sa.text(
                "UPDATE bank_transactions SET pointage_type_id = :nouveau, updated_at = now() "
                "WHERE id = :id"
            ),
            {"nouveau": nouveau, "id": operation.id},
        )
        connection.execute(
            sa.text(
                "INSERT INTO audit_logs (user_id, action, entite, entite_id, ancienne_valeur, "
                "nouvelle_valeur) VALUES (NULL, 'repointage', 'bank_transaction', :id, "
                "CAST(:avant AS jsonb), CAST(:apres AS jsonb))"
            ),
            {
                "id": str(operation.id),
                "avant": json.dumps(
                    {"pointage": libelles.get(operation.pointage_type_id)}, ensure_ascii=False
                ),
                "apres": json.dumps(
                    {"pointage": libelles.get(nouveau), "origine": "Migration 0017"},
                    ensure_ascii=False,
                ),
            },
        )


def downgrade() -> None:
    op.execute(
        "UPDATE pointage_types SET actif = true, updated_at = now() "
        "WHERE code IN ('ENCAISSEMENT', 'DECAISSEMENT', 'FRAIS_BANCAIRES')"
    )
    # Les catégories créées restent (des opérations peuvent les porter) ; le code reste à 60
