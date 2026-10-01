"""Tests for the FastAPI route table after health-era retirement."""

from app.main import app


def test_app_route_paths_exclude_context_and_predict() -> None:
    paths = [route.path for route in app.routes if hasattr(route, "path")]
    assert all(not path.startswith("/context") for path in paths)
    assert all(not path.startswith("/predict") for path in paths)
