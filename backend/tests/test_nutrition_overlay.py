from app.domain.nutrition import USDA_NUTRITION_NOTICE
from app.domain.nutrition_catalog import NUTRITION, NUTRITION_BASIS_G
from app.services.grocery_planner import PlanEstimate, ShoppingLine
from app.services.nutrition_overlay import nutrition_for_plan


def shopping_line(ingredient_id: str) -> ShoppingLine:
    return ShoppingLine(
        ingredient_id=ingredient_id,
        name=ingredient_id,
        unit="g",
        quantity=250,
        packages=1,
        cost_cents=1,
        from_pantry=False,
    )


def make_plan(*lines: ShoppingLine, total_cents: int | None = 999) -> PlanEstimate:
    return PlanEstimate(
        lines=lines,
        total_cents=total_cents,
        accepted=True,
        warnings=(),
        catalog_version="sample-prices-v1",
        notice="unused planner notice",
    )


def test_known_ingredients_copy_facts_and_leave_plan_total() -> None:
    grocery_plan = make_plan(
        shopping_line("chicken_breast"),
        shopping_line("eggs"),
        total_cents=999,
    )
    chicken = NUTRITION["chicken_breast"]
    eggs = NUTRITION["eggs"]

    result = nutrition_for_plan(grocery_plan)

    assert result.notice == USDA_NUTRITION_NOTICE
    assert result.basis_g == NUTRITION_BASIS_G
    assert result.basis_g == 100
    assert grocery_plan.total_cents == 999
    assert result.items is not None
    assert len(result.items) == 2
    assert result.items[0].ingredient_id == "chicken_breast"
    assert result.items[0].fdc_id == chicken.fdc_id
    assert result.items[0].energy_kcal == chicken.energy_kcal
    assert result.items[1].ingredient_id == "eggs"
    assert result.items[1].fdc_id == eggs.fdc_id
    assert result.items[1].energy_kcal == eggs.energy_kcal


def test_unknown_ingredient_yields_none_items() -> None:
    grocery_plan = make_plan(shopping_line("unknown_food"))

    result = nutrition_for_plan(grocery_plan)

    assert result.items is None
    assert result.notice == USDA_NUTRITION_NOTICE
    assert result.basis_g == NUTRITION_BASIS_G


def test_empty_lines_yield_empty_items() -> None:
    grocery_plan = make_plan()

    result = nutrition_for_plan(grocery_plan)

    assert result.items == ()
    assert result.notice == USDA_NUTRITION_NOTICE
    assert result.basis_g == NUTRITION_BASIS_G
