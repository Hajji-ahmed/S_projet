from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SaisieDevise, SaisiePrevision, SaisiePrevisionJour


def list_devises(db: Session, company_id: int, jour: date) -> list[SaisieDevise]:
    query = select(SaisieDevise).where(
        SaisieDevise.company_id == company_id, SaisieDevise.jour == jour
    )
    return list(db.scalars(query.order_by(SaisieDevise.id)))


def list_previsions(db: Session, company_id: int, depuis: date) -> list[SaisiePrevision]:
    """Cellules des lignes datées `depuis` ou plus tard, par date puis par rang."""
    query = select(SaisiePrevision).where(
        SaisiePrevision.company_id == company_id, SaisiePrevision.jour >= depuis
    )
    return list(
        db.scalars(query.order_by(SaisiePrevision.jour, SaisiePrevision.ligne, SaisiePrevision.id))
    )


def list_previsions_jour(db: Session, company_id: int, depuis: date) -> list[SaisiePrevisionJour]:
    """Encaissement / Escompte / Douane des lignes datées `depuis` ou plus tard."""
    query = select(SaisiePrevisionJour).where(
        SaisiePrevisionJour.company_id == company_id, SaisiePrevisionJour.jour >= depuis
    )
    return list(db.scalars(query.order_by(SaisiePrevisionJour.jour, SaisiePrevisionJour.ligne)))


def add(db: Session, row: object) -> None:
    db.add(row)


def delete(db: Session, row: object) -> None:
    db.delete(row)
