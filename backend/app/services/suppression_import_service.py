"""Suppression d'un import (décision du 23/10/2026) : tout ce qu'un fichier a apporté, relevé bancaire
ou export Sage, avec un motif obligatoire. Tout ou rien, et vérifié avant la première écriture :

- une ligne rapprochée (validée, y compris par la comptabilisation SIMTIS des frais) bloque : le
  message donne les codes à annuler d'abord ;
- un relevé : seul le dernier import du compte se supprime (les soldes des relevés suivants ne
  dépendent jamais d'un relevé disparu), sauf un fichier d'opérations en cours, hors de cet
  enchaînement ;
- les propositions en attente de ces lignes sont retirées (leurs autres lignes redeviennent « Non
  rapprochée »), comme l'historique des propositions rejetées ou annulées qui les citent.

Le lot d'import reste, au statut « Annulé » : le journal garde la trace du fichier, et le même
fichier peut être réimporté (l'unicité ne porte que sur les imports confirmés).
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import BankStatement, ImportBatch
from app.repositories import (
    accounting_repository,
    balance_repository,
    import_repository,
    reconciliation_repository,
)
from app.services import audit_service
from app.services.errors import ConflictError, NotFoundError

STATUT_ANNULE = "Annulé"
MOTIF_MIN, MOTIF_MAX = 3, 500
# Nombre de codes cités dans le message de refus
CODES_CITES = 10


@dataclass(frozen=True)
class Suppression:
    nb_lignes: int
    nb_propositions_retirees: int


def motif_obligatoire(motif: str) -> str:
    motif = (motif or "").strip()
    if len(motif) < MOTIF_MIN:
        raise ConflictError("Indiquez le motif de la suppression.")
    return motif[:MOTIF_MAX]


def liberer(db: Session, tx_ids: list[int], entry_ids: list[int]) -> int:
    """Refuse si une ligne est rapprochée ; sinon retire les correspondances qui citent ces lignes
    (propositions en attente, rejets, annulations) et libère leurs autres lignes. Retourne le
    nombre de propositions retirées."""
    matches = reconciliation_repository.matches_touching(db, tx_ids, entry_ids)
    validees = sorted(m.code or f"n° {m.id}" for m in matches if m.statut == "Validée")
    if validees:
        cites = ", ".join(validees[:CODES_CITES])
        reste = f" et {len(validees) - CODES_CITES} autre(s)" if len(validees) > CODES_CITES else ""
        raise ConflictError(
            f"{len(validees)} rapprochement(s) validé(s) utilisent des lignes de cet import "
            f"({cites}{reste}) : annulez-les d'abord dans l'Historique du rapprochement. "
            "Rien n'a été supprimé."
        )
    supprimees_tx, supprimees_ecr = set(tx_ids), set(entry_ids)
    autres_tx: set[int] = set()
    autres_ecr: set[int] = set()
    propositions = 0
    for match in matches:
        if match.statut != "Proposée":
            continue
        propositions += 1
        for item in match.items:
            if item.bank_transaction_id and item.bank_transaction_id not in supprimees_tx:
                autres_tx.add(item.bank_transaction_id)
            if item.accounting_entry_id and item.accounting_entry_id not in supprimees_ecr:
                autres_ecr.add(item.accounting_entry_id)
    reconciliation_repository.delete_matches(db, [m.id for m in matches])
    reconciliation_repository.liberer_lignes(db, sorted(autres_tx), sorted(autres_ecr))
    return propositions


def _batch(db: Session, batch_id: int | None) -> ImportBatch:
    batch = db.get(ImportBatch, batch_id) if batch_id is not None else None
    if batch is None:
        raise NotFoundError("Import introuvable.")
    if batch.statut == STATUT_ANNULE:
        raise ConflictError("Cet import est déjà supprimé.")
    return batch


def raison_releve_non_supprimable(db: Session, statement: BankStatement) -> str | None:
    """Pourquoi ce relevé ne peut pas être supprimé maintenant (None : il peut l'être). Les lignes
    rapprochées ne sont vérifiées qu'à la suppression (elle donne alors leurs codes)."""
    batch = db.get(ImportBatch, statement.import_batch_id) if statement.import_batch_id else None
    if batch is None or batch.statut == STATUT_ANNULE:
        return "Import déjà supprimé."
    if statement.en_cours:
        return None
    dernier = import_repository.dernier_releve(db, statement.bank_account_id)
    if dernier is not None and dernier.id != statement.id:
        return "Supprimez d'abord les imports plus récents de ce compte."
    return None


def supprimer_releve(
    db: Session, statement_id: int, *, motif: str, acteur_id: int, ip: str | None
) -> Suppression:
    statement = import_repository.get_statement(db, statement_id)
    if statement is None:
        raise NotFoundError("Relevé introuvable.")
    motif = motif_obligatoire(motif)
    reconciliation_repository.lock_company(db, statement.bank_account.company_id)
    batch = _batch(db, statement.import_batch_id)
    raison = raison_releve_non_supprimable(db, statement)
    if raison:
        raise ConflictError(raison)

    tx_ids = import_repository.transaction_ids_of_statement(db, statement.id)
    propositions = liberer(db, tx_ids, [])
    import_repository.delete_transactions(db, tx_ids)
    import_repository.delete_balance_checks(db, statement.id)
    # Le solde du jour écrit par ce relevé (source « Relevé ») disparait avec lui
    if statement.periode_fin and statement.solde_cloture is not None:
        jour = balance_repository.get(db, statement.bank_account_id, statement.periode_fin)
        if jour and jour.source == "Relevé" and jour.solde == statement.solde_cloture:
            if jour.credit_utilise is None:
                db.delete(jour)
            else:
                jour.solde, jour.source = None, "Saisie"
    batch.statut = STATUT_ANNULE
    audit_service.log(
        db,
        user_id=acteur_id,
        action="suppression_import",
        entite="import_batch",
        entite_id=batch.id,
        avant={
            "type": batch.type,
            "fichier": batch.fichier_nom,
            "bank_account_id": statement.bank_account_id,
            "periode_debut": statement.periode_debut,
            "periode_fin": statement.periode_fin,
            "solde_cloture": statement.solde_cloture,
            "nb_operations": len(tx_ids),
            "en_cours": statement.en_cours,
        },
        apres={"statut": STATUT_ANNULE, "motif": motif, "propositions_retirees": propositions},
        ip=ip,
    )
    db.commit()
    return Suppression(len(tx_ids), propositions)


def supprimer_import_comptable(
    db: Session, batch_id: int, *, motif: str, type_import: str, acteur_id: int, ip: str | None
) -> Suppression:
    batch = db.get(ImportBatch, batch_id)
    if batch is None or batch.type != type_import:
        raise NotFoundError("Import introuvable.")
    motif = motif_obligatoire(motif)
    reconciliation_repository.lock_company(db, batch.company_id)
    batch = _batch(db, batch.id)

    entry_ids = accounting_repository.entry_ids_of_batch(db, batch.id)
    debut, fin = accounting_repository.periode_of_entries(db, entry_ids)
    propositions = liberer(db, [], entry_ids)
    accounting_repository.delete_entries(db, entry_ids)
    batch.statut = STATUT_ANNULE
    audit_service.log(
        db,
        user_id=acteur_id,
        action="suppression_import",
        entite="import_batch",
        entite_id=batch.id,
        avant={
            "type": batch.type,
            "fichier": batch.fichier_nom,
            "periode_debut": debut,
            "periode_fin": fin,
            "nb_ecritures": len(entry_ids),
        },
        apres={"statut": STATUT_ANNULE, "motif": motif, "propositions_retirees": propositions},
        ip=ip,
    )
    db.commit()
    return Suppression(len(entry_ids), propositions)
