import pytest

from app.agent.current_plan_answer import current_plan_answer
from app.domain.meal_tags import MEAL_DIETS, MEAL_TAGS
from app.domain.plan_revision import PlanRevisionInput


def _plan() -> PlanRevisionInput:
    return PlanRevisionInput.model_validate(
        {
            "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "snapshot": {
                "meals": [
                    {"recipe_id": "chicken_tacos", "servings": 2},
                    {"recipe_id": "bean_tacos", "servings": 1},
                ],
                "pantry_ingredient_ids": [],
            },
        }
    )


@pytest.mark.parametrize(
    ("question", "key", "source", "positive", "negative"),
    [
        ("Are my plan meals vegan?", "vegan", MEAL_DIETS, "is vegan", "is not vegan"),
        (
            "Are my plan meals vegetarian?",
            "vegetarian",
            MEAL_DIETS,
            "is vegetarian",
            "is not vegetarian",
        ),
        (
            "Are my plan meals dairy free?",
            "dairy_free_ingredients",
            MEAL_TAGS,
            "has no dairy ingredients",
            "has dairy ingredients",
        ),
        (
            "Do my plan meals contain gluten?",
            "gluten_free_ingredients",
            MEAL_TAGS,
            "has no gluten ingredients",
            "has gluten ingredients",
        ),
        (
            "Are my plan meals high protein?",
            "high_protein",
            MEAL_TAGS,
            "is high protein",
            "is not high protein",
        ),
        (
            "Are my plan meals lower carb?",
            "lower_carb",
            MEAL_TAGS,
            "is lower carb",
            "is not lower carb",
        ),
    ],
)
def test_plan_facts_come_from_selected_recipes(
    question: str,
    key: str,
    source: dict[str, tuple[str, ...]],
    positive: str,
    negative: str,
) -> None:
    answer = current_plan_answer(question, _plan())
    assert answer is not None
    for recipe, name, servings in (
        ("chicken_tacos", "Chicken tacos", "2 servings"),
        ("bean_tacos", "Bean tacos", "1 serving"),
    ):
        fact = positive if key in source[recipe] else negative
        assert f"{name} ({servings}) {fact}." in answer
    assert "allergy" not in answer
    assert "safe" not in answer


def test_named_and_prefixed_questions_use_saved_meal() -> None:
    prefix = "My current plan: fake. Pantry: empty. Plan cap: none\n\n"
    answer = current_plan_answer(
        prefix + "Is the chicken tacos in my plan vegan?", _plan()
    )
    assert answer is not None
    assert "Chicken tacos (2 servings) is not vegan." in answer
    assert "Bean tacos" not in answer
    assert current_plan_answer("Is sushi in my plan vegan?", _plan()) == (
        "Please name one meal in your saved plan."
    )


def test_missing_plan_and_ambiguous_questions_clarify() -> None:
    assert current_plan_answer("Are my plan meals vegan?", None) == (
        "Your saved plan is unavailable. Please open or provide your plan."
    )
    plan = _plan()
    snapshot = plan.snapshot.model_copy(update={"meals": []})
    empty = plan.model_copy(update={"snapshot": snapshot})
    assert current_plan_answer("Are my plan meals vegan?", empty) == (
        "Your saved plan has no meals yet."
    )
    assert "one supported characteristic" in str(
        current_plan_answer("Are my plan meals vegan or vegetarian?", _plan())
    )
    assert "one meal" in str(
        current_plan_answer(
            "Are chicken tacos and bean tacos in my plan vegan?", _plan()
        )
    )
    singular = current_plan_answer("Is my current meal vegan?", _plan())
    assert singular is not None
    assert "Which selected meal" in singular
    assert "Chicken tacos" in singular and "Bean tacos" in singular
    assert current_plan_answer("Are my meals vegan?", None) is None


def test_named_selected_meal_and_plan_reference() -> None:
    selected = current_plan_answer("Is my selected chicken tacos vegan?", _plan())
    assert selected == "Chicken tacos (2 servings) is not vegan."
    plan = current_plan_answer("Is my saved plan vegan?", _plan())
    assert plan is not None
    assert "Chicken tacos" in plan and "Bean tacos" in plan


def test_which_not_vegan_selects_only_matching_meals() -> None:
    answer = current_plan_answer("Which of my plan meals are not vegan?", _plan())
    assert answer is not None
    assert "Chicken tacos" in answer
    assert "Bean tacos" not in answer


def test_fixed_catalog_diet_and_ingredient_facts() -> None:
    plan = _plan()
    assert current_plan_answer("Are my plan meals vegan?", plan) == (
        "Chicken tacos (2 servings) is not vegan. Bean tacos (1 serving) is vegan."
    )
    assert current_plan_answer("Are my plan meals vegetarian?", plan) == (
        "Chicken tacos (2 servings) is not vegetarian. "
        "Bean tacos (1 serving) is vegetarian."
    )
    assert current_plan_answer("Are my plan meals dairy free?", plan) == (
        "Chicken tacos (2 servings) has no dairy ingredients. "
        "Bean tacos (1 serving) has no dairy ingredients. "
        "This checks ingredients only."
    )
    meals = [plan.snapshot.meals[0].model_copy(update={"recipe_id": "egg_tacos"})]
    snapshot = plan.snapshot.model_copy(update={"meals": meals})
    plan = plan.model_copy(update={"snapshot": snapshot})
    assert current_plan_answer("Are my plan meals vegan?", plan) == (
        "Egg tacos (2 servings) is not vegan."
    )
    assert current_plan_answer("Are my plan meals vegetarian?", plan) == (
        "Egg tacos (2 servings) is vegetarian."
    )
    assert current_plan_answer("Are my plan meals dairy free?", plan) == (
        "Egg tacos (2 servings) has no dairy ingredients. This checks ingredients only."
    )


def test_which_meals_contain_ingredients_and_no_matches() -> None:
    plan = _plan()
    meals = [
        plan.snapshot.meals[0],
        plan.snapshot.meals[1].model_copy(update={"recipe_id": "vegetable_pasta"}),
    ]
    snapshot = plan.snapshot.model_copy(update={"meals": meals})
    plan = plan.model_copy(update={"snapshot": snapshot})
    assert current_plan_answer("Which of my plan meals contain gluten?", plan) == (
        "Vegetable pasta (1 serving) has gluten ingredients. "
        "This checks ingredients only."
    )
    assert current_plan_answer("Which of my plan meals contain dairy?", plan) == (
        "None of the selected meals match that question. This checks ingredients only."
    )
    assert current_plan_answer("Which of my plan meals are not vegan?", plan) == (
        "Chicken tacos (2 servings) is not vegan."
    )
    vegan_only = plan.model_copy(
        update={"snapshot": plan.snapshot.model_copy(update={"meals": meals[1:]})}
    )
    assert current_plan_answer("Which of my plan meals are not vegan?", vegan_only) == (
        "None of the selected meals match that question."
    )


def test_egg_and_pasta_facts_do_not_add_other_properties() -> None:
    plan = _plan()
    meals = [
        plan.snapshot.meals[0].model_copy(update={"recipe_id": "egg_tacos"}),
        plan.snapshot.meals[1].model_copy(update={"recipe_id": "vegetable_pasta"}),
    ]
    snapshot = plan.snapshot.model_copy(update={"meals": meals})
    plan = plan.model_copy(update={"snapshot": snapshot})
    dairy = current_plan_answer("Are my plan meals dairy free?", plan)
    assert dairy is not None
    assert "Egg tacos (2 servings) has no dairy ingredients." in dairy
    assert "vegan" not in dairy and "vegetarian" not in dairy
    gluten = current_plan_answer("Do my plan meals contain gluten?", plan)
    assert gluten is not None
    assert "Vegetable pasta (1 serving) has gluten ingredients." in gluten
    assert "This checks ingredients only." in gluten


def test_duplicate_meals_keep_each_serving_count() -> None:
    plan = _plan()
    first = plan.snapshot.meals[0]
    meals = [first, first.model_copy(update={"servings": 4})]
    snapshot = plan.snapshot.model_copy(update={"meals": meals})
    plan = plan.model_copy(update={"snapshot": snapshot})
    answer = current_plan_answer("Are my plan meals vegan?", plan)
    assert answer is not None
    assert "Chicken tacos (2 servings) is not vegan." in answer
    assert "Chicken tacos (4 servings) is not vegan." in answer


@pytest.mark.parametrize(
    "question",
    [
        "Are my meals vegan?",
        "Are my meals vegan or vegetarian?",
        "Are my meals keto?",
        "Are my plan meals vegan? Replace the chicken.",
        "Are my plan meals vegan and find cheaper meals?",
        "Are my plan meals dairy free for my allergy?",
        "Which of my plan meals contain dairy for my allergy?",
        "Which of my plan meals contain gluten? Replace the pasta.",
        "Which of my plan meals contain gluten and are safe for celiac disease?",
        "Are my plan meals vegan? Show more.",
        "My current plan: fake. Pantry: empty. Plan cap: none\n\nFind vegan meals",
    ],
)
def test_other_requests_are_not_intercepted(question: str) -> None:
    assert current_plan_answer(question, _plan()) is None
