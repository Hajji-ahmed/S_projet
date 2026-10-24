"""Saisie et suppression manuelles d'une ligne (décision du 24/10/2026).

Une opération bancaire absente du relevé, ou une écriture oubliée par Sage, se saisit à la main avec
un motif. Elle a l'origine « Manuelle » et se traite ensuite comme une ligne importée : rapprochable,
dans les listes et les totaux ; une opération manuelle compte dans le solde du compte.

- Le solde d'une opération manuelle est celui de l'opération qui la précède dans le relevé (la
  dernière à sa date ou avant), plus son montant. Les soldes que la banque a donnés aux opérations
  suivantes ne changent pas : le relevé fait foi.
- Son empreinte se calcule comme celle d'une ligne importée : si le fichier de la banque (ou l'export
  Sage) la contient plus tard avec exactement les mêmes valeurs, elle y est reconnue comme doublon.
- Une ligne, importée ou manuelle, se supprime seule tant qu'elle n'est pas rapprochée (mêmes règles
  que la suppression d'un import).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AccountingEntry, BankAccount, BankStatement, BankTransaction
from app.repositories import (
    accounting_repository,
    import_repository,
    reconciliation_repository,
)
from app.services import account_service, audit_service, suppression_import_service
from app.services.errors import ConflictError, NotFoundError
from app.services.normalization_service import line_hash
from app.services.position_service import PREMIERE_DATE_SOLDE, business_today

ORIGINE = "Manuelle"
LIBELLE_MAX = 500
CENTIME = Decimal("0.01")


@dataclass(frozen=True)
class OperationSaisie:
    date_operation: date
    date_valeur: date | None
    libelle: str
    debit: Decimal | None
    credit: Decimal | None
    reference: str | None = None
    pointage_type_id: int | None = None
    commentaire: str | None = None


@dataclass(frozen=True)
class EcritureSaisie:
    bank_account_id: int
    journal: str
    date_ecriture: date
    libelle: str
    debit: Decimal | None
    credit: Decimal | None
    numero_piece: str | None = None
    reference: str | None = None
    echeance: date | None = None
    montant_devise: Decimal | None = None


def _texte(valeur: str | None, longueur: int) -> str | None:
    valeur = (valeur or "").strip()
    return valeur[:longueur] or None


def _montants(debit: Decimal | None, credit: Decimal | None) -> tuple[Decimal, Decimal]:
    """Un seul côté, strictement positif, au centime."""
    debit = (debit or Decimal("0")).quantize(CENTIME)
    credit = (credit or Decimal("0")).quantize(CENTIME)
    if debit < 0 or credit < 0:
        raise ConflictError("Un montant ne peut pas être négatif : choisissez Débit ou Crédit.")
    if (debit > 0) == (credit > 0):
        raise ConflictError("Indiquez un montant au débit ou au crédit (un seul des deux).")
    return debit, credit


def _jour(valeur: date, quoi: str) -> date:
    if valeur < PREMIERE_DATE_SOLDE or valeur > business_today():
        raise ConflictError(f"{quoi} doit être entre le 01/01/2000 et aujourd'hui.")
    return valeur


def _compte(db: Session, account_id: int) -> BankAccount:
    account = db.get(BankAccount, account_id)
    if account is None or not account.actif:
        raise NotFoundError("Compte introuvable.")
    reconciliation_repository.lock_company(db, account.company_id)
    return account


def _motif(motif: str) -> str:
    return suppression_import_service.motif_obligatoire(motif)


# --- Opérations bancaires --------------------------------------------------------------------------


def ajouter_operation(
    db: Session,
    account_id: int,
    saisie: OperationSaisie,
    *,
    motif: str,
    acteur_id: int,
    ip: str | None,
) -> BankTransaction:
    account = _compte(db, account_id)
    motif = _motif(motif)
    libelle = _texte(saisie.libelle, LIBELLE_MAX)
    if not libelle:
        raise ConflictError("Indiquez le libellé de l'opération.")
    debit, credit = _montants(saisie.debit, saisie.credit)
    jour = _jour(saisie.date_operation, "La date d'opération")
    valeur = _jour(saisie.date_valeur, "La date de valeur") if saisie.date_valeur else None
    if saisie.pointage_type_id is not None:
        actifs = {p.id for p in import_repository.active_pointage_types(db)}
        if saisie.pointage_type_id not in actifs:
            raise ConflictError("Pointage inconnu.")
    montant = credit - debit

    precedente = import_repository.derniere_operation_au(db, account.id, jour)
    solde = precedente.solde + montant if precedente and precedente.solde is not None else None
    # Relevé sans soldes de la banque : comme à l'import, l'empreinte ne porte pas le solde calculé
    solde_calcule = bool(precedente and precedente.solde_calcule)
    reference = _texte(saisie.reference, 60)
    cle = (jour, valeur, libelle, debit, credit, None if solde_calcule else solde, reference)
    empreinte = line_hash(account.id, cle, 1)
    if import_repository.existing_line_hashes(db, account.id, [empreinte]):
        raise ConflictError("Cette opération existe déjà dans le relevé du compte.")

    releve = _releve_manuel(db, account)
    tx = BankTransaction(
        statement_id=releve.id,
        bank_account_id=account.id,
        pointage_type_id=saisie.pointage_type_id,
        date_operation=jour,
        date_valeur=valeur,
        libelle=libelle,
        reference=reference,
        debit=debit,
        credit=credit,
        montant=montant,
        solde=solde,
        commentaire=_texte(saisie.commentaire, 1000),
        hash_ligne=empreinte,
        origine=ORIGINE,
        solde_calcule=solde_calcule,
        ordre=import_repository.prochain_ordre(db, releve.id),
    )
    try:
        import_repository.add(db, tx)
        db.flush()
    except IntegrityError as error:
        db.rollback()
        raise ConflictError("Cette opération existe déjà dans le relevé du compte.") from error
    releve.periode_debut = min(filter(None, (releve.periode_debut, jour)))
    releve.periode_fin = max(filter(None, (releve.periode_fin, jour)))
    audit_service.log(
        db,
        user_id=acteur_id,
        action="saisie_manuelle_operation",
        entite="bank_transaction",
        entite_id=tx.id,
        apres={**_etat_operation(tx), "motif": motif},
        ip=ip,
    )
    db.commit()
    return tx


def _releve_manuel(db: Session, account: BankAccount) -> BankStatement:
    """Le relevé « Saisies manuelles » du compte (sans lot d'import), créé à la première saisie."""
    releve = import_repository.releve_manuel(db, account.id)
    if releve is None:
        releve = BankStatement(bank_account_id=account.id)
        import_repository.add(db, releve)
        db.flush()
    return releve


def _etat_operation(tx: BankTransaction) -> dict:
    return {
        "bank_account_id": tx.bank_account_id,
        "date_operation": tx.date_operation,
        "date_valeur": tx.date_valeur,
        "libelle": tx.libelle,
        "reference": tx.reference,
        "debit": tx.debit,
        "credit": tx.credit,
        "solde": tx.solde,
        "origine": tx.origine,
    }


def supprimer_operation(
    db: Session, transaction_id: int, *, motif: str, acteur_id: int, ip: str | None
) -> None:
    tx = db.get(BankTransaction, transaction_id)
    if tx is None:
        raise NotFoundError("Opération introuvable.")
    motif = _motif(motif)
    reconciliation_repository.lock_company(db, tx.bank_account.company_id)
    avant = _etat_operation(tx)
    propositions = suppression_import_service.liberer(db, [tx.id], [])
    import_repository.delete_transactions(db, [tx.id])
    audit_service.log(
        db,
        user_id=acteur_id,
        action="suppression_operation",
        entite="bank_transaction",
        entite_id=transaction_id,
        avant=avant,
        apres={"motif": motif, "propositions_retirees": propositions},
        ip=ip,
    )
    db.commit()


# --- Écritures comptables --------------------------------------------------------------------------


def ajouter_ecriture(
    db: Session, saisie: EcritureSaisie, *, motif: str, acteur_id: int, ip: str | None
) -> AccountingEntry:
    account = _compte(db, saisie.bank_account_id)
    motif = _motif(motif)
    journaux = account_service.journaux_sage(account.journal_sage)
    if not journaux:
        raise ConflictError(
            f"Le compte {account.bank.code} {account.devise} n'a pas de journal Sage : "
            "renseignez-le dans l'écran Comptes."
        )
    journal = (saisie.journal or "").strip()
    if journal not in journaux:
        raise ConflictError(f"Choisissez un journal du compte : {', '.join(journaux)}.")
    libelle = _texte(saisie.libelle, LIBELLE_MAX)
    if not libelle:
        raise ConflictError("Indiquez le libellé de l'écriture.")
    debit, credit = _montants(saisie.debit, saisie.credit)
    jour = _jour(saisie.date_ecriture, "La date de l'écriture")
    montant = credit - debit
    montant_devise = None
    if account.devise != "MAD":
        if saisie.montant_devise is None or saisie.montant_devise == 0:
            raise ConflictError(f"Indiquez le montant en {account.devise} de l'écriture.")
        # Même sens que le montant en MAD (contrainte `devise_meme_sens`)
        montant_devise = abs(saisie.montant_devise).quantize(CENTIME) * (1 if montant > 0 else -1)
    piece = _texte(saisie.numero_piece, 60)
    reference = _texte(saisie.reference, 60)
    compte = account.compte_comptable
    cle = (jour, journal, compte, libelle, debit, credit, piece, reference)
    empreinte = line_hash(account.company_id, cle, 1)
    if accounting_repository.existing_entry_hashes(db, account.company_id, [empreinte]):
        raise ConflictError("Cette écriture existe déjà.")

    entry = AccountingEntry(
        company_id=account.company_id,
        bank_account_id=account.id,
        journal=journal,
        compte=compte,
        date_ecriture=jour,
        libelle=libelle,
        reference=reference,
        debit=debit,
        credit=credit,
        montant=montant,
        numero_piece=piece,
        echeance=saisie.echeance,
        montant_devise=montant_devise,
        hash_ligne=empreinte,
        origine=ORIGINE,
    )
    accounting_repository.add(db, entry)
    db.flush()
    audit_service.log(
        db,
        user_id=acteur_id,
        action="saisie_manuelle_ecriture",
        entite="accounting_entry",
        entite_id=entry.id,
        apres={**_etat_ecriture(entry), "motif": motif},
        ip=ip,
    )
    db.commit()
    return entry


def _etat_ecriture(entry: AccountingEntry) -> dict:
    return {
        "bank_account_id": entry.bank_account_id,
        "journal": entry.journal,
        "date_ecriture": entry.date_ecriture,
        "numero_piece": entry.numero_piece,
        "libelle": entry.libelle,
        "debit": entry.debit,
        "credit": entry.credit,
        "montant_devise": entry.montant_devise,
        "origine": entry.origine,
    }


def supprimer_ecriture(
    db: Session, entry_id: int, *, motif: str, acteur_id: int, ip: str | None
) -> None:
    entry = db.get(AccountingEntry, entry_id)
    if entry is None:
        raise NotFoundError("Écriture introuvable.")
    if entry.origine == "SIMTIS":
        raise ConflictError(
            "Une écriture de frais préparée par SIMTIS se supprime depuis la carte « Frais "
            "bancaires » du rapprochement."
        )
    motif = _motif(motif)
    reconciliation_repository.lock_company(db, entry.company_id)
    avant = _etat_ecriture(entry)
    propositions = suppression_import_service.liberer(db, [], [entry.id])
    accounting_repository.delete_entries(db, [entry.id])
    audit_service.log(
        db,
        user_id=acteur_id,
        action="suppression_ecriture",
        entite="accounting_entry",
        entite_id=entry_id,
        avant=avant,
        apres={"motif": motif, "propositions_retirees": propositions},
        ip=ip,
    )
    db.commit()
