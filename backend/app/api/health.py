from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.health import HealthResponse
from app.services import health_service

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    return health_service.check_health(db)
