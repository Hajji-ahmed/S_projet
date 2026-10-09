"""CORS : origines autorisées à appeler l'API depuis un navigateur."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app

LOCAL = "http://192.168.137.1:3000"


def preflight(app, origin: str):
    with TestClient(app) as client:
        return client.options(
            "/api/health",
            headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
        )


@pytest.fixture
def app_with(monkeypatch):
    def build(**env):
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        get_settings.cache_clear()
        return create_app()

    yield build
    get_settings.cache_clear()


def test_only_the_listed_origin_is_accepted_by_default(app_with):
    app = app_with(CORS_ORIGINS="http://localhost:3000", CORS_ORIGIN_REGEX="")

    assert preflight(app, "http://localhost:3000").headers.get("access-control-allow-origin") == (
        "http://localhost:3000"
    )
    assert "access-control-allow-origin" not in preflight(app, LOCAL).headers


def test_a_local_network_pattern_lets_a_phone_or_another_pc_in(app_with):
    app = app_with(
        CORS_ORIGINS="http://localhost:3000",
        CORS_ORIGIN_REGEX=r"http://192\.168\.\d{1,3}\.\d{1,3}:3000",
    )

    assert preflight(app, LOCAL).headers.get("access-control-allow-origin") == LOCAL
    assert "access-control-allow-origin" not in preflight(app, "http://evil.example").headers
