from collections.abc import Iterator
from pathlib import Path

import pytest

from app.deps import get_kroger_client, get_supermarket_estimator
from app.main import app
from app.provider_settings import GroceryProviderSettings
from app.providers.kroger import KrogerClient

PLAN_RESULT: dict[str, object] = {
    "plan": {
        "lines": [
            {
                "ingredient_id": "chicken_breast",
                "unit": "g",
                "quantity": 100,
                "from_pantry": False,
            }
        ]
    }
}


class FixedEstimator:
    def estimate_ingredient_cents(
        self, ingredient_id: int, amount: int, unit: str
    ) -> int | None:
        del ingredient_id, amount, unit
        return 150


class ForbiddenEstimator:
    def estimate_ingredient_cents(
        self, ingredient_id: int, amount: int, unit: str
    ) -> int | None:
        del ingredient_id, amount, unit
        raise AssertionError("estimator")


def override_estimator(estimator: object | None) -> None:
    app.dependency_overrides[get_supermarket_estimator] = lambda: estimator


def clear_estimator_override() -> None:
    app.dependency_overrides.pop(get_supermarket_estimator, None)


def test_get_supermarket_estimator_none_without_key_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_supermarket_estimator.cache_clear()
    monkeypatch.setattr(
        "app.deps.load_provider_settings",
        lambda: GroceryProviderSettings(),
    )

    def boom(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("build_spoonacular")

    monkeypatch.setattr("app.deps.build_spoonacular", boom)
    assert get_supermarket_estimator() is None
    get_supermarket_estimator.cache_clear()


@pytest.fixture(autouse=True)
def _clear_kroger_cache() -> Iterator[None]:
    get_kroger_client.cache_clear()
    yield
    get_kroger_client.cache_clear()


def test_get_kroger_client_none_without_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.deps.load_provider_settings", lambda: GroceryProviderSettings()
    )
    assert get_kroger_client() is None


def test_get_kroger_client_none_when_files_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "app.deps.load_provider_settings",
        lambda: GroceryProviderSettings(
            kroger_client_id_file=tmp_path / "no-id",
            kroger_secret_file=tmp_path / "no-secret",
        ),
    )
    assert get_kroger_client() is None


def test_get_kroger_client_built_from_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    id_file = tmp_path / "id"
    secret_file = tmp_path / "secret"
    id_file.write_text("invented-id\n")
    secret_file.write_text("invented-secret\n")
    id_file.chmod(0o600)
    secret_file.chmod(0o600)
    monkeypatch.setattr(
        "app.deps.load_provider_settings",
        lambda: GroceryProviderSettings(
            kroger_client_id_file=id_file, kroger_secret_file=secret_file
        ),
    )
    client = get_kroger_client()
    assert isinstance(client, KrogerClient)
    assert get_kroger_client() is client
