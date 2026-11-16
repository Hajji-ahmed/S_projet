"""Écriture Sage corrigée dans Sage, alignée sur place (16/11/2026) : `python -m app.cli
corriger-ecriture-sage`. Une ligne modifiée dans Sage (libellé, référence…) a une nouvelle empreinte :
au grand livre suivant, l'ancienne écriture est « absente » et la ligne corrigée « à importer ». Si
l'ancienne est dans un rapprochement validé (une reprise de 3 804 lignes, par exemple), la supprimer
oblige à annuler tout le rapprochement. La commande recopie plutôt la ligne corrigée du grand livre
sur l'écriture : même compte, journal, date, N° pièce, débit et crédit ; l'écriture garde son id,
son statut et son rapprochement, et la ligne du fichier devient un doublon au réimport."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AccountingEntry, Company
from app.repositories import accounting_repository, auth_repository
from app.services import accounting_import_service, audit_service
from app.services.accounting_import_service import EntryLine
from app.services.errors import ConflictError, NotFoundError

# Champs recopiés de la ligne du grand livre ; le montant, la date et la pièce ne changent pas
CHAMPS = ("libelle", "reference", "compte", "echeance", "tiers", "hash_ligne")


@dataclass
class Bilan:
    societe: str
    ecriture_id: int
    ligne: int  # numéro de la ligne Excel retenue
    code_rapprochement: str | None
    avant: dict[str, object] = field(default_factory=dict)
    apres: dict[str, object] = field(default_factory=dict)  # seulement les champs qui changent


def _decrire(line: EntryLine) -> str:
    montant = line.debit if line.debit else -(line.credit or Decimal("0"))
    return (
        f"ligne {line.numero} · {line.date_ecriture:%d/%m/%Y} · {line.numero_piece or '—'} · "
        f"{line.libelle} · {montant}"
    )


def candidates(entry: AccountingEntry, lines: list[EntryLine]) -> list[EntryLine]:
    """Pure : lignes à importer du fichier qui ont la place de l'écriture (même compte bancaire,
    journal, date, N° pièce, débit et crédit)."""
    return [
        line
        for line in lines
        if line.statut == "Valide"
        and line.bank_account_id == entry.bank_account_id
        and line.journal == entry.journal
        and line.date_ecriture == entry.date_ecriture
        and (line.numero_piece or None) == (entry.numero_piece or None)
        and (line.debit or Decimal("0")) == entry.debit
        and (line.credit or Decimal("0")) == entry.credit
    ]


def analyser(
    db: Session,
    *,
    code_societe: str,
    fichier_nom: str,
    content: bytes,
    ecriture_id: int,
    ligne: int | None = None,
    feuille: str | None = None,
) -> Bilan:
    """Ne modifie pas la base."""
    company = db.scalar(select(Company).filter_by(code=code_societe))
    if company is None:
        raise NotFoundError(f"Société introuvable : {code_societe}.")
    entry = db.get(AccountingEntry, ecriture_id)
    if entry is None or entry.company_id != company.id:
        raise NotFoundError(f"Écriture {ecriture_id} introuvable pour {company.nom}.")
    analysis = accounting_import_service.analyse_entries(
        db, company_id=company.id, fichier_nom=fichier_nom, content=content, feuille=feuille
    )
    if analysis.erreurs_mapping:
        raise ConflictError(" ".join(analysis.erreurs_mapping))
    if entry.id not in {absente.id for absente in analysis.ecritures_absentes}:
        raise ConflictError(
            f"L'écriture {entry.id} n'est pas absente de ce grand livre : rien à corriger."
        )

    found = candidates(entry, analysis.lignes)
    if ligne is not None:
        found = [line for line in found if line.numero == ligne]
        if not found:
            raise ConflictError(
                f"La ligne {ligne} n'est pas une ligne à importer de même compte, journal, date, "
                f"N° pièce et montant que l'écriture {entry.id}."
            )
    if not found:
        raise ConflictError(
            f"Aucune ligne à importer du fichier n'a la même date, le même N° pièce et le même "
            f"montant que l'écriture {entry.id} : elle a été supprimée de Sage, pas corrigée."
        )
    if len(found) > 1:
        liste = " ; ".join(_decrire(line) for line in found)
        raise ConflictError(f"Plusieurs lignes possibles, indiquez --ligne : {liste}.")
    line = found[0]

    bilan = Bilan(
        societe=company.nom,
        ecriture_id=entry.id,
        ligne=line.numero,
        code_rapprochement=accounting_repository.codes_valides(db, [entry.id]).get(entry.id),
    )
    for champ in CHAMPS:
        avant, apres = getattr(entry, champ), getattr(line, champ)
        if avant != apres:
            bilan.avant[champ], bilan.apres[champ] = avant, apres
    return bilan


def appliquer(
    db: Session,
    *,
    code_societe: str,
    fichier_nom: str,
    content: bytes,
    ecriture_id: int,
    motif: str,
    email: str,
    ligne: int | None = None,
    feuille: str | None = None,
) -> Bilan:
    """Recopie la ligne corrigée sur l'écriture, avec un audit, en une transaction."""
    if not motif.strip():
        raise ConflictError("Indiquez le motif de la correction.")
    user = auth_repository.get_user_by_email(db, email)
    if user is None or not user.actif:
        raise NotFoundError(f"Utilisateur introuvable ou inactif : {email}.")
    bilan = analyser(
        db,
        code_societe=code_societe,
        fichier_nom=fichier_nom,
        content=content,
        ecriture_id=ecriture_id,
        ligne=ligne,
        feuille=feuille,
    )
    entry = db.get(AccountingEntry, ecriture_id)
    for champ, valeur in bilan.apres.items():
        setattr(entry, champ, valeur)
    audit_service.log(
        db,
        user_id=user.id,
        action="correction_ecriture_sage",
        entite="accounting_entry",
        entite_id=entry.id,
        avant=bilan.avant,
        apres={
            **bilan.apres,
            "fichier": fichier_nom,
            "ligne": bilan.ligne,
            "rapprochement": bilan.code_rapprochement,
            "motif": motif.strip(),
        },
    )
    db.commit()
    return bilan


def afficher(bilan: Bilan) -> list[str]:
    """Lignes du compte rendu de la commande."""
    texte = [
        f"{bilan.societe}, écriture {bilan.ecriture_id} ← ligne {bilan.ligne} du fichier",
        f"Rapprochement conservé : {bilan.code_rapprochement or 'aucun'}",
    ]
    for champ, apres in bilan.apres.items():
        avant = bilan.avant[champ]
        if isinstance(avant, date) or isinstance(apres, date):
            avant = f"{avant:%d/%m/%Y}" if avant else None
            apres = f"{apres:%d/%m/%Y}" if apres else None
        texte.append(f"  {champ} : {avant!r} → {apres!r}")
    if not bilan.apres:
        texte.append("  Aucun champ ne change.")
    return texte
