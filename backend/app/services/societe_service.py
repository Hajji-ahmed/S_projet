"""Gestion des sociétés par l'administrateur (17/11/2026) : création, renommage, activation.

Le code est immuable après la création (les seeds retrouvent les sociétés par leur code). Une
société n'est jamais supprimée : la désactiver la retire du sélecteur et garde toutes ses données.
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Company
from app.repositories import account_repository
from app.services import audit_service
from app.services.errors import ConflictError, NotFoundError


def _get_or_404(db: Session, company_id: int) -> Company:
    company = account_repository.get_company(db, company_id)
    if company is None:
        raise NotFoundError("Société introuvable.")
    return company


def _check_nom_libre(db: Session, nom: str, sauf_id: int | None = None) -> None:
    existante = account_repository.company_by_nom(db, nom)
    if existante is not None and existante.id != sauf_id:
        raise ConflictError(f"Une société s'appelle déjà « {existante.nom} ».")


def list_all(db: Session) -> list[Company]:
    return account_repository.list_all_companies(db)


def create(db: Session, *, code: str, nom: str, acteur_id: int, ip: str | None = None) -> Company:
    """`code` et `nom` arrivent nettoyés par le schéma (majuscules, espaces retirés)."""
    if account_repository.company_by_code(db, code) is not None:
        raise ConflictError(f"Le code {code} est déjà utilisé par une autre société.")
    _check_nom_libre(db, nom)

    company = Company(code=code, nom=nom, actif=True)
    try:
        account_repository.add_company(db, company)
    except IntegrityError as error:  # création simultanée du même code
        db.rollback()
        raise ConflictError(f"Le code {code} est déjà utilisé par une autre société.") from error

    audit_service.log(
        db,
        user_id=acteur_id,
        action="creation_societe",
        entite="company",
        entite_id=company.id,
        apres={"code": company.code, "nom": company.nom, "actif": True},
        ip=ip,
    )
    db.commit()
    return company


def update(
    db: Session,
    company_id: int,
    *,
    nom: str | None,
    actif: bool | None,
    acteur_id: int,
    ip: str | None = None,
) -> Company:
    """Renomme et / ou active ou désactive. Toutes les règles sont vérifiées avant toute
    modification ; seuls les champs réellement changés sont tracés."""
    company = _get_or_404(db, company_id)
    renommer = nom is not None and nom != company.nom
    changer_statut = actif is not None and actif != company.actif

    if renommer:
        _check_nom_libre(db, nom, sauf_id=company.id)
    if changer_statut and not actif and account_repository.count_active_companies(db) <= 1:
        raise ConflictError("Il doit rester au moins une société active.")

    if renommer:
        avant = company.nom
        company.nom = nom
        audit_service.log(
            db,
            user_id=acteur_id,
            action="modification_societe",
            entite="company",
            entite_id=company.id,
            avant={"nom": avant},
            apres={"nom": nom},
            ip=ip,
        )
    if changer_statut:
        company.actif = actif
        audit_service.log(
            db,
            user_id=acteur_id,
            action="reactivation_societe" if actif else "desactivation_societe",
            entite="company",
            entite_id=company.id,
            avant={"actif": not actif},
            apres={"actif": actif},
            ip=ip,
        )
    if renommer or changer_statut:
        db.commit()
    return company
