from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.repositories import health_repository
from app.schemas.health import HealthResponse


def check_health(db: Session) -> HealthResponse:
    try:
        health_repository.ping(db)
    except SQLAlchemyError:
        return HealthResponse(status="degraded", database="error")
    return HealthResponse(status="ok", database="ok")
