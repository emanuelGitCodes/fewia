from collections.abc import Mapping
from dataclasses import dataclass

from app.domain.budget import BudgetResult
from app.domain.catalog import CATALOG_VERSION, INGREDIENTS, RECIPES, Ingredient, Recipe
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE, GroceryRequest


class PlanningError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ShoppingLine:
    ingredient_id: str
    name: str
    unit: str
    quantity: int
    packages: int
    cost_cents: int | None
    from_pantry: bool


@dataclass(frozen=True, slots=True)
class PlanEstimate:
    lines: tuple[ShoppingLine, ...]
    total_cents: int | None
    accepted: bool
    warnings: tuple[str, ...]
    catalog_version: str
    notice: str


def _validate_budget(budget: BudgetResult) -> int:
    if type(budget.available_cents) is not int:
        raise TypeError("budget.available_cents must be an integer")
    if budget.available_cents < 0:
        raise ValueError("budget.available_cents must be non-negative")
    return budget.available_cents


def _validate_ids(
    ids: list[str], ingredients: Mapping[str, Ingredient], field_name: str
) -> frozenset[str]:
    for ingredient_id in ids:
        if ingredient_id not in ingredients:
            raise PlanningError(f"unknown {field_name} ingredient id: {ingredient_id}")
    return frozenset(ids)


def plan_groceries(
    request: GroceryRequest,
    budget: BudgetResult,
    *,
    ingredients: Mapping[str, Ingredient] = INGREDIENTS,
    recipes: Mapping[str, Recipe] = RECIPES,
) -> PlanEstimate:
    if not isinstance(budget, BudgetResult):
        raise TypeError("budget must be a BudgetResult")
    available_cents = _validate_budget(budget)
    pantry = _validate_ids(request.pantry_ingredients, ingredients, "pantry")
    exclusions = _validate_ids(request.ingredient_exclusions, ingredients, "exclusion")

    quantities: dict[str, int] = {}
    for meal in request.meals:
        if meal.recipe_id not in recipes:
            raise PlanningError(f"recipe is missing from catalog: {meal.recipe_id}")
        recipe = recipes[meal.recipe_id]
        for ingredient_id, per_serving_quantity in recipe.ingredients:
            if ingredient_id not in ingredients:
                raise PlanningError(
                    f"ingredient is missing from catalog: {ingredient_id}"
                )
            if type(per_serving_quantity) is not int or per_serving_quantity <= 0:
                raise PlanningError(f"ingredient quantity is invalid: {ingredient_id}")
            ingredient = ingredients[ingredient_id]
            if ingredient_id in exclusions:
                raise PlanningError(f"ingredient is excluded: {ingredient_id}")
            if (request.diet == "vegetarian" and not ingredient.vegetarian) or (
                request.diet == "vegan" and not ingredient.vegan
            ):
                raise PlanningError(f"ingredient conflicts with diet: {ingredient_id}")
            quantities[ingredient_id] = quantities.get(ingredient_id, 0) + (
                per_serving_quantity * meal.servings
            )

    lines: list[ShoppingLine] = []
    total_cents: int | None = 0
    missing_price = False
    for ingredient_id in sorted(quantities):
        ingredient = ingredients[ingredient_id]
        quantity = quantities[ingredient_id]
        if ingredient_id in pantry:
            lines.append(
                ShoppingLine(
                    ingredient_id,
                    ingredient.name,
                    ingredient.unit,
                    quantity,
                    0,
                    0,
                    True,
                )
            )
            continue
        if (
            type(ingredient.package_quantity) is not int
            or ingredient.package_quantity <= 0
        ):
            raise PlanningError(f"package quantity is invalid: {ingredient_id}")
        packages = (
            quantity + ingredient.package_quantity - 1
        ) // ingredient.package_quantity
        price = ingredient.price_cents
        if price is not None and (type(price) is not int or price < 0):
            raise PlanningError(f"purchase price is invalid: {ingredient_id}")
        cost_cents = None if price is None else packages * price
        if cost_cents is None:
            missing_price = True
        elif total_cents is not None:
            total_cents += cost_cents
        lines.append(
            ShoppingLine(
                ingredient_id,
                ingredient.name,
                ingredient.unit,
                quantity,
                packages,
                cost_cents,
                False,
            )
        )

    if missing_price:
        total_cents = None
    warnings = list(budget.warnings)
    if missing_price:
        warnings.append("A purchase price is missing, so this estimate is incomplete.")
    if total_cents is not None and total_cents > available_cents:
        warnings.append("The estimate exceeds the available budget.")
    accepted = total_cents is not None and total_cents <= available_cents
    return PlanEstimate(
        tuple(lines),
        total_cents,
        accepted,
        tuple(warnings),
        CATALOG_VERSION,
        SAMPLE_ESTIMATE_NOTICE,
    )
