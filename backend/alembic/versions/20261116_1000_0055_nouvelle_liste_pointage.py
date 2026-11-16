"""nouvelle liste de pointage

Revision ID: 0055
Revises: 0054
Create Date: 2026-11-16 10:00:00

Décision du 16/11/2026 : la liste de pointage du métier (« Pointage position.xlsx », 46 catégories
+ « À analyser ») remplace les 74 catégories du 08/10/2026. Cette migration
1. crée les 47 nouvelles catégories (s'il en manque) ;
2. désactive toutes les autres : elles restent sur les opérations déjà pointées (rien n'est
   re-pointé), ne sont plus proposées et ne nourrissent plus la mémoire du pointage automatique ;
3. crée la règle `POINTAGE_CONFIRMATIONS` (N = 1) : un libellé reçoit automatiquement le pointage
   que Salma lui a donné au moins N fois.

La liste est recopiée ici, figée (source : `app/seeds/pointages.py`). Le downgrade réactive les 74
catégories du 08/10/2026 et désactive les nouvelles (sans les supprimer : des opérations peuvent les
porter), puis supprime la règle.
"""

import re
import unicodedata
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0055"
down_revision: str | None = "0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATEGORIES = (
    "Solde à nouveau", "Cheque interne compte à compte",
    "Real Time Gross Settlement (RTGS) compte à compte",
    "Mouvement compte courant associé encaissé", "Mouvement compte courant associé décaissé",
    "Chèque client encaissé", "Effet client encaissé", "Versement client encaissé",
    "Virement client encaissé", "Chèque intra-groupe prêt décaissé",
    "Chèque intra-groupe emprunt encaissé", "Rapatriement client etranger encaissé",
    "Impayé / rejet client décaissé", "Effet client escompté", "Effet intra-groupe emprunt escompté",
    "Effet intra-groupe emprunt encaissé", "Autres valeurs encaissées",
    "Déblocage crédit moyen terme (CMT) encaissé", "Échéance Crédit moyen terme (CMT) décaissé",
    "Tombée refinancement en devise décaissé",
    "Tombée refinancement en devise avec interet décaissé", "Tombée refinancement en MAD décaissé",
    "Déblocage crédit refinancement en MAD encaissé", "Déblocage crédit spot encaissé",
    "Échéance crédit spot décaissé", "Échéance crédit spot avec interet décaissé",
    "Échéance leasing décaissé", "Allimentation caisse SIMTIS encaissé",
    "Autres valeurs décaissées", "Agios d'escompte décaissé", "Agios d'échelle décaissé",
    "Intérêts débiteurs refinancement en devise décaissé",
    "Intérêts débiteurs refinancement en MAD décaissé", "Intérêts débiteurs crédit spot décaissé",
    "Droit de timbre décaissé", "Commissions et frais bancaires décaissé",
    "Tva/commissions et frais bancaires décaissé", "Paiement par cartes bancaires décaissé",
    "Restitutions bancaires encaissé", "Effet fournisseur décaissé", "Chéque fournisseur décaissé",
    "Virement fournisseur décaissé", "Virement fournisseur étranger décaissé",
    "Virement électronique décaissé", "Impôts et taxes DGI décaissé", "Charges sociales décaissé",
    "À analyser",
)  # fmt: skip
# Les 74 catégories du 08/10/2026 (migration 0017), réactivées par le downgrade
ANCIENNES = (
    "A_NOUVEAU", "A_VOIR", "AGIOS", "AGIOS_D_ECHELLE", "BOURSE", "CARTE_MASSARIF",
    "CERTIFICATION_CHEQUE", "CHEQUE_DE_BANQUE", "CHEQUE_SOFT", "CHQ_ISMAIL_KABBAJ", "CHQ_ZAI",
    "CLIENT_ETRANGER", "CMT_16M", "CMT_25M", "CMT_32M", "CMT_40M", "CMT_70M", "CNSS", "COM",
    "CREDIT_OXYGENE", "DGI", "DOUANE", "DROIT", "ENCAISSEMENT_CLIENT", "ENCAISSEMENT_HORS_GROUP",
    "ENCAISSEMENT_HORS_GROUP_ALLIANCE_INDUSTRIELLE", "ENCAISSEMENT_HORS_GROUP_DECATHLON",
    "ENCAISSEMENT_SOFT", "ENCAISSEMENT_SOFTTECH", "ESCOMPTE_HORS_GROUP",
    "ESCOMPTE_HORS_GROUP_SOFTRETAIL", "ESCOMPTE_SOFTRETAIL", "ESCOMPTE_SOFTRETAIL_SOFTTECH", "FRAIS",
    "FRAIS_D_APPROCHE", "FRAIS_RETENUE_A_LA_SOURCE", "FRS_LOCAL", "IMP_CLIENT", "INTERET",
    "LA_PAIE", "LEASE_BACK", "MAGASINAGE", "MAROC_OUTDOOR", "MISE_A_DISPOSITION", "MSC",
    "PAIEMENT_PAR_CARTE", "REDEVANCE", "REFIN", "REFIN_EN_MAD", "REJET", "REMBOURSEMENT_PRET",
    "RESTITUTION_FRAIS_BANCAIRE", "RESTITUTION_IMP_ESCOMPTE", "RESTITUTION_INTERETS_DEBITEURS_ACNE",
    "RESTITUTION_INTERETS_DEBITEURS_FC", "RETENUE_A_LA_SOURCE", "RTGS", "RTGS_ISMAIL_KABBAJ",
    "SIMTIS_SIMTIS", "SIMTIS_SIMTIS_TEFIL_SIMTIS", "SIMTIS_TEFIL", "SPOT", "SRM", "SURESTARIES",
    "TCA", "TEFIL_SIMTIS", "TEFIL_TEFIL", "TVA", "VERSEMENT_ISMAIL_KABBAJ", "VIGNETTE", "VIR_CNSS",
    "VIR_ETRANGER", "VIR_ISMAIL_KABBAJ", "ZAI",
)  # fmt: skip
_NON_ALNUM = re.compile(r"[^A-Z0-9]+")


def _code(libelle: str) -> str:
    raw = unicodedata.normalize("NFKD", libelle)
    plain = "".join(char for char in raw if not unicodedata.combining(char)).upper()
    return "_".join(_NON_ALNUM.sub(" ", plain).split())


CODES = tuple(_code(libelle) for libelle in CATEGORIES)


def _activer(connection: sa.Connection, codes: Sequence[str], actif: bool, *, sauf: bool) -> None:
    condition = "code NOT IN :codes" if sauf else "code IN :codes"
    connection.execute(
        sa.text(
            f"UPDATE pointage_types SET actif = :actif, updated_at = now() "
            f"WHERE {condition} AND actif <> :actif"
        ).bindparams(sa.bindparam("codes", expanding=True)),
        {"codes": list(codes), "actif": actif},
    )


def upgrade() -> None:
    connection = op.get_bind()
    # Le compteur d'identifiants peut être en retard sur les lignes (insérées avec leur id)
    connection.execute(
        sa.text(
            "SELECT setval(pg_get_serial_sequence('pointage_types', 'id'), "
            "coalesce(max(id), 0) + 1, false) FROM pointage_types"
        )
    )
    for code, libelle in zip(CODES, CATEGORIES, strict=True):
        connection.execute(
            sa.text(
                "INSERT INTO pointage_types (code, libelle) VALUES (:code, :libelle) "
                "ON CONFLICT (code) DO NOTHING"
            ),
            {"code": code, "libelle": libelle},
        )
    _activer(connection, CODES, True, sauf=False)
    _activer(connection, CODES, False, sauf=True)
    connection.execute(
        sa.text(
            "INSERT INTO reconciliation_rules (code, libelle, critere, poids, tolerance, actif) "
            "VALUES ('POINTAGE_CONFIRMATIONS', 'Confirmations avant pointage automatique', "
            "'pointage', 0, 1, true) ON CONFLICT (code) DO NOTHING"
        )
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text("DELETE FROM reconciliation_rules WHERE code = 'POINTAGE_CONFIRMATIONS'")
    )
    _activer(connection, CODES, False, sauf=False)
    _activer(connection, ANCIENNES, True, sauf=False)
