from datetime import date

from sqlalchemy import func, select
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


def dernier_rang_previsions(db: Session, company_id: int, jours: set[date]) -> dict[date, int]:
    """Rang le plus élevé déjà utilisé à chacune de ces dates (cellules ou montants sans banque)."""
    if not jours:
        return {}
    rangs: dict[date, int] = {}
    for model in (SaisiePrevision, SaisiePrevisionJour):
        query = (
            select(model.jour, func.max(model.ligne))
            .where(model.company_id == company_id, model.jour.in_(jours))
            .group_by(model.jour)
        )
        for jour, rang in db.execute(query):
            rangs[jour] = max(rangs.get(jour, 0), rang)
    return rangs


def add(db: Session, row: object) -> None:
    db.add(row)


def delete(db: Session, row: object) -> None:
    db.delete(row)
