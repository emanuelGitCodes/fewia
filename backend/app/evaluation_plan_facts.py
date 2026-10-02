from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.domain.catalog import CATALOG_VERSION, INGREDIENTS, RECIPES
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE, GroceryRequest

_CHECKS = (
    "ingredient_coverage",
    "quantities",
    "package_rounding",
    "sample_costs",
    "diet",
    "exclusions",
    "total_cents",
    "acceptance",
    "budget_cap",
    "notice",
    "catalog_version",
    "schema",
)


class _Line(BaseModel):
    model_config = ConfigDict(strict=True)

    ingredient_id: str
    name: str
    unit: str
    quantity: int = Field(gt=0)
    packages: int = Field(ge=0)
    cost_cents: int | None = Field(ge=0)
    from_pantry: bool


class _Plan(BaseModel):
    model_config = ConfigDict(strict=True)

    lines: list[_Line]
    total_cents: int | None = Field(ge=0)
    accepted: bool
    catalog_version: str
    notice: str


class _Budget(BaseModel):
    model_config = ConfigDict(strict=True)

    available_cents: int = Field(ge=0)
    pending_cents: int
    stale: bool


class _Observation(BaseModel):
    model_config = ConfigDict(strict=True)

    request: GroceryRequest
    plan: _Plan
    budget: _Budget


def plan_integrity(result: dict[str, object]) -> dict[str, bool]:
    checks = dict.fromkeys(_CHECKS, False)
    try:
        observation = _Observation.model_validate(result)
    except ValidationError:
        return checks
    request, plan, budget = (
        observation.request,
        observation.plan,
        observation.budget,
    )
    if any(
        item not in INGREDIENTS
        for item in request.pantry_ingredients + request.ingredient_exclusions
    ) or any(meal.recipe_id not in RECIPES for meal in request.meals):
        return checks
    quantities: dict[str, int] = {}
    for meal in request.meals:
        for ingredient_id, amount in RECIPES[meal.recipe_id].ingredients:
            quantities[ingredient_id] = (
                quantities.get(ingredient_id, 0) + amount * meal.servings
            )
    checks["schema"] = True
    checks["notice"] = plan.notice == SAMPLE_ESTIMATE_NOTICE
    checks["catalog_version"] = plan.catalog_version == CATALOG_VERSION
    ids = [line.ingredient_id for line in plan.lines]
    checks["ingredient_coverage"] = len(ids) == len(set(ids)) and set(ids) == set(
        quantities
    )
    checks["diet"] = all(
        request.diet == "omnivore"
        or (request.diet == "vegetarian" and INGREDIENTS[item].vegetarian)
        or (request.diet == "vegan" and INGREDIENTS[item].vegan)
        for item in quantities
    )
    checks["exclusions"] = not set(quantities).intersection(
        request.ingredient_exclusions
    )
    if not checks["ingredient_coverage"]:
        return checks
    checks.update(quantities=True, package_rounding=True, sample_costs=True)
    expected_total = 0
    missing_price = False
    for line in plan.lines:
        ingredient = INGREDIENTS[line.ingredient_id]
        quantity = quantities[line.ingredient_id]
        pantry = line.ingredient_id in request.pantry_ingredients
        packages = (
            0
            if pantry
            else (quantity + ingredient.package_quantity - 1)
            // ingredient.package_quantity
        )
        price = ingredient.price_cents
        cost = None if price is None else packages * price
        if pantry:
            cost = 0
        checks["quantities"] &= (
            line.quantity == quantity
            and line.name == ingredient.name
            and line.unit == ingredient.unit
            and line.from_pantry == pantry
        )
        checks["package_rounding"] &= line.packages == packages
        if cost is None:
            missing_price = True
            checks["sample_costs"] &= (
                line.cost_cents is None
                and plan.total_cents is None
                and not plan.accepted
            )
        else:
            checks["sample_costs"] &= line.cost_cents == cost
            expected_total += cost
    checks["total_cents"] = (
        plan.total_cents is None
        if missing_price
        else plan.total_cents == expected_total
    ) and checks["sample_costs"]
    cap = request.plan_cap_cents
    affordable = (
        not missing_price
        and checks["total_cents"]
        and expected_total <= budget.available_cents
        and (cap is None or expected_total <= cap)
    )
    checks["acceptance"] = plan.accepted == affordable
    checks["budget_cap"] = not plan.accepted or (
        not missing_price and (cap is None or expected_total <= cap)
    )
    return checks
