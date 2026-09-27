from collections.abc import Mapping

from app.domain.spoonacular_catalog import SPOONACULAR_IDS
from app.domain.supermarket_estimate import SPOONACULAR_COST_NOTICE, SupermarketLine
from app.providers.spoonacular import SpoonacularUnavailable
from app.services.grocery_planner import PlanEstimate, ShoppingLine
from app.services.supermarket_overlay import (
    attach_supermarket_estimate,
    estimate_supermarket_cost,
)

CHICKEN_ID = SPOONACULAR_IDS["chicken_breast"]
EGG_ID = SPOONACULAR_IDS["eggs"]
RICE_ID = SPOONACULAR_IDS["rice"]


class FakeEstimator:
    def __init__(
        self,
        cents_by_id: Mapping[int, int | None],
        *,
        error: type[BaseException] | None = None,
        error_on_call: int | None = None,
    ) -> None:
        self.cents_by_id = dict(cents_by_id)
        self.error = error
        self.error_on_call = error_on_call
        self.calls: list[tuple[int, int, str]] = []

    def estimate_ingredient_cents(
        self, ingredient_id: int, amount: int, unit: str
    ) -> int | None:
        self.calls.append((ingredient_id, amount, unit))
        if self.error is not None and (
            self.error_on_call is None or len(self.calls) == self.error_on_call
        ):
            raise self.error()
        return self.cents_by_id[ingredient_id]


def shopping_line(
    ingredient_id: str,
    unit: str,
    quantity: int,
    *,
    from_pantry: bool = False,
) -> ShoppingLine:
    return ShoppingLine(
        ingredient_id=ingredient_id,
        name=ingredient_id,
        unit=unit,
        quantity=quantity,
        packages=0 if from_pantry else 1,
        cost_cents=0 if from_pantry else 1,
        from_pantry=from_pantry,
    )


def make_plan(
    *lines: ShoppingLine,
    total_cents: int | None = 999,
    accepted: bool = True,
) -> PlanEstimate:
    return PlanEstimate(
        lines=lines,
        total_cents=total_cents,
        accepted=accepted,
        warnings=(),
        catalog_version="sample-prices-v1",
        notice="unused planner notice",
    )


def test_sums_purchase_lines_and_leaves_plan_total() -> None:
    grocery_plan = make_plan(
        shopping_line("chicken_breast", "g", 100),
        shopping_line("eggs", "each", 2),
        total_cents=999,
    )
    estimator = FakeEstimator({CHICKEN_ID: 150, EGG_ID: 50})

    result = estimate_supermarket_cost(grocery_plan, estimator)

    assert result.total_cents == 200
    assert grocery_plan.total_cents == 999
    assert result.notice == SPOONACULAR_COST_NOTICE
    assert estimator.calls == [(CHICKEN_ID, 100, "g"), (EGG_ID, 2, "piece")]
    assert result.lines == (
        SupermarketLine("chicken_breast", 150),
        SupermarketLine("eggs", 50),
    )


def test_skips_pantry_lines() -> None:
    grocery_plan = make_plan(
        shopping_line("chicken_breast", "g", 100, from_pantry=True),
        shopping_line("eggs", "each", 2),
    )
    estimator = FakeEstimator({EGG_ID: 50})

    result = estimate_supermarket_cost(grocery_plan, estimator)

    assert result.total_cents == 50
    assert estimator.calls == [(EGG_ID, 2, "piece")]
    assert result.notice == SPOONACULAR_COST_NOTICE
    assert result.lines == (SupermarketLine("eggs", 50),)


def test_none_estimate_makes_overlay_none_and_keeps_accepted() -> None:
    grocery_plan = make_plan(shopping_line("eggs", "each", 1), accepted=True)
    estimator = FakeEstimator({EGG_ID: None})

    result = estimate_supermarket_cost(grocery_plan, estimator)

    assert result.total_cents is None
    assert grocery_plan.accepted is True
    assert result.notice == SPOONACULAR_COST_NOTICE


def test_unavailable_makes_overlay_none() -> None:
    grocery_plan = make_plan(shopping_line("eggs", "each", 1))
    estimator = FakeEstimator({EGG_ID: 50}, error=SpoonacularUnavailable)

    result = estimate_supermarket_cost(grocery_plan, estimator)

    assert result.total_cents is None
    assert result.notice == SPOONACULAR_COST_NOTICE


def test_unknown_unit_or_missing_id_makes_overlay_none() -> None:
    estimator = FakeEstimator({EGG_ID: 50})

    unknown_unit = estimate_supermarket_cost(
        make_plan(shopping_line("eggs", "ml", 1)), estimator
    )
    missing_id = estimate_supermarket_cost(
        make_plan(shopping_line("eggs", "each", 1)),
        estimator,
        ids={},
    )
    invalid_id = estimate_supermarket_cost(
        make_plan(shopping_line("eggs", "each", 1)),
        estimator,
        ids={"eggs": 0},
    )

    assert unknown_unit.total_cents is None
    assert missing_id.total_cents is None
    assert invalid_id.total_cents is None
    assert estimator.calls == []
    assert unknown_unit.notice == SPOONACULAR_COST_NOTICE
    assert missing_id.notice == SPOONACULAR_COST_NOTICE
    assert invalid_id.notice == SPOONACULAR_COST_NOTICE


def test_no_purchase_lines_total_zero() -> None:
    grocery_plan = make_plan(shopping_line("salt", "g", 5, from_pantry=True))
    estimator = FakeEstimator({})

    result = estimate_supermarket_cost(grocery_plan, estimator)

    assert result.total_cents == 0
    assert estimator.calls == []
    assert result.notice == SPOONACULAR_COST_NOTICE
    assert result.lines == ()


def test_missing_id_line_keeps_other_line_cents() -> None:
    grocery_plan = make_plan(
        shopping_line("chicken_breast", "g", 100),
        shopping_line("unknown_spice", "g", 10),
        shopping_line("eggs", "each", 2),
    )
    estimator = FakeEstimator({CHICKEN_ID: 150, EGG_ID: 50})

    result = estimate_supermarket_cost(grocery_plan, estimator)

    assert result.total_cents is None
    assert result.lines == (
        SupermarketLine("chicken_breast", 150),
        SupermarketLine("unknown_spice", None),
        SupermarketLine("eggs", 50),
    )
    assert estimator.calls == [(CHICKEN_ID, 100, "g"), (EGG_ID, 2, "piece")]


def test_unavailable_stops_later_estimator_calls() -> None:
    grocery_plan = make_plan(
        shopping_line("chicken_breast", "g", 100),
        shopping_line("eggs", "each", 2),
        shopping_line("rice", "g", 80),
    )
    estimator = FakeEstimator(
        {CHICKEN_ID: 150, EGG_ID: 50, RICE_ID: 80},
        error=SpoonacularUnavailable,
        error_on_call=2,
    )

    result = estimate_supermarket_cost(grocery_plan, estimator)

    assert result.total_cents is None
    assert result.lines == (
        SupermarketLine("chicken_breast", 150),
        SupermarketLine("eggs", None),
        SupermarketLine("rice", None),
    )
    assert estimator.calls == [(CHICKEN_ID, 100, "g"), (EGG_ID, 2, "piece")]


def _plan_result(*lines: dict[str, object]) -> dict[str, object]:
    return {"plan": {"lines": list(lines)}, "keep": 1}


def _purchase(
    ingredient_id: str, unit: str, quantity: int, *, from_pantry: bool = False
) -> dict[str, object]:
    return {
        "ingredient_id": ingredient_id,
        "unit": unit,
        "quantity": quantity,
        "from_pantry": from_pantry,
    }


def test_attach_adds_supermarket_estimate_shape() -> None:
    result = _plan_result(
        _purchase("chicken_breast", "g", 100),
        _purchase("eggs", "each", 2, from_pantry=True),
    )
    estimator = FakeEstimator({CHICKEN_ID: 150})

    attached = attach_supermarket_estimate(result, estimator)

    assert attached["supermarket_estimate"] == {
        "total_cents": 150,
        "notice": SPOONACULAR_COST_NOTICE,
        "lines": [{"ingredient_id": "chicken_breast", "cents": 150}],
    }
    assert estimator.calls == [(CHICKEN_ID, 100, "g")]


def test_attach_does_not_mutate_result() -> None:
    result = _plan_result(_purchase("chicken_breast", "g", 100))
    estimator = FakeEstimator({CHICKEN_ID: 150})

    attached = attach_supermarket_estimate(result, estimator)

    assert "supermarket_estimate" not in result
    assert result["keep"] == 1
    assert attached is not result
    assert attached["plan"] is result["plan"]
    assert attached["keep"] == 1


def test_attach_skips_malformed_plan() -> None:
    estimator = FakeEstimator({EGG_ID: 50})
    missing_plan = {"other": 1}
    not_dict = {"plan": []}
    missing_id = _plan_result(
        {"unit": "each", "quantity": 1, "from_pantry": False},
    )

    missing_out = attach_supermarket_estimate(missing_plan, estimator)
    not_dict_out = attach_supermarket_estimate(not_dict, estimator)
    missing_id_out = attach_supermarket_estimate(missing_id, estimator)

    assert missing_out == {"other": 1}
    assert "supermarket_estimate" not in missing_out
    assert missing_out is not missing_plan
    assert not_dict_out == {"plan": []}
    assert "supermarket_estimate" not in not_dict_out
    assert "supermarket_estimate" not in missing_id_out
    assert missing_id_out["keep"] == 1
    assert estimator.calls == []


def test_attach_skips_zero_quantity_line() -> None:
    result = _plan_result(
        _purchase("chicken_breast", "g", 100),
        _purchase("eggs", "each", 0),
    )
    estimator = FakeEstimator({CHICKEN_ID: 150, EGG_ID: 50})

    attached = attach_supermarket_estimate(result, estimator)

    assert attached == result
    assert attached is not result
    assert "supermarket_estimate" not in attached
    assert estimator.calls == []


def test_attach_skips_negative_quantity_line() -> None:
    result = _plan_result(
        _purchase("chicken_breast", "g", 100),
        _purchase("eggs", "each", -5),
    )
    estimator = FakeEstimator({CHICKEN_ID: 150, EGG_ID: 50})

    attached = attach_supermarket_estimate(result, estimator)

    assert attached == result
    assert attached is not result
    assert "supermarket_estimate" not in attached
    assert estimator.calls == []
