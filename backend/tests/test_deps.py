import pytest

from app.deps import get_supermarket_estimator
from app.main import app
from app.provider_settings import GroceryProviderSettings

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
