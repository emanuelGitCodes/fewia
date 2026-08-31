"""Tests for the health endpoint."""

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)


def test_healthz_returns_ok() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_settings_have_a_default_database_url() -> None:
    assert settings.database_url.startswith("postgresql+psycopg://")
