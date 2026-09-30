from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.db import get_db
from app.main import app

client = TestClient(app)


def test_health_ok_when_database_reachable():
    """Nécessite PostgreSQL (le service `db` de Docker Compose, ou celui de la CI)."""
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_degraded_when_database_unreachable():
    class BrokenSession:
        def execute(self, *args, **kwargs):
            raise OperationalError("SELECT 1", {}, Exception("connexion refusée"))

    def broken_db() -> Iterator[BrokenSession]:
        yield BrokenSession()

    app.dependency_overrides[get_db] = broken_db
    try:
        response = client.get("/api/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "degraded", "database": "error"}


def test_unknown_route_returns_404():
    assert client.get("/api/does-not-exist").status_code == 404
