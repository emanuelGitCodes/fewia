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
    assert current_plan_answer("Are my meals vegan?", None) == (
        "Your saved plan is unavailable. Please open or provide your plan."
    )


@pytest.mark.parametrize(
    "question",
    [
        "Are chicken tacos and bean tacos in my plan vegan?",
        "Which of chicken tacos and bean tacos in my plan are vegetarian?",
        "Do chicken tacos and bean tacos in my plan contain gluten?",
        "Are my selected chicken tacos and bean tacos vegan?",
        "Are chicken tacos and bean tacos and vegetable pasta in my plan vegan?",
    ],
)
def test_named_meal_lists_ask_for_one_meal(question: str) -> None:
    assert current_plan_answer(question, _plan()) == (
        "Please name one meal in your saved plan."
    )


@pytest.mark.parametrize(
    "question",
    [
        "Are my selected chicken tacos and sushi vegan?",
        "Which of the saved sushi and bean tacos are vegetarian?",
        "Do planned sushi and ramen contain gluten?",
        "Are chicken tacos and sushi in my plan vegan?",
    ],
)
def test_named_meal_lists_clarify_without_matching_names_or_plan(
    question: str,
) -> None:
    assert current_plan_answer(question, _plan()) == (
        "Please name one meal in your saved plan."
    )
    assert current_plan_answer(question, None) == (
        "Your saved plan is unavailable. Please open or provide your plan."
    )


@pytest.mark.parametrize("plan_available", [False, True])
@pytest.mark.parametrize(
    "question",
    [
        "Are my selected chicken tacos and buy sushi vegan?",
        "Are my saved sushi and swap bean tacos vegetarian?",
        "Are my selected chicken tacos and sushi vegan and find cheaper meals?",
        "Do planned sushi and ramen contain gluten for my allergy?",
        "Are my selected chicken tacos and sushi vegan? Buy them.",
    ],
)
def test_named_meal_lists_keep_other_requests(
    question: str, plan_available: bool
) -> None:
    assert current_plan_answer(question, _plan() if plan_available else None) is None


@pytest.mark.parametrize(
    "question",
    [
        "Are chicken tacos in my plan vegan and bean tacos in my plan vegan?",
        "Are chicken tacos and bean tacos in my plan vegan and find cheaper meals?",
        "Do chicken tacos and bean tacos in my plan contain gluten and add rice?",
        "Are chicken tacos and swap bean tacos in my plan vegan?",
        "Are chicken tacos and buy bean tacos in my plan vegan?",
        "Are chicken tacos and bean tacos in my plan vegan for my allergy?",
        "Are chicken tacos and bean tacos in my plan vegan? Buy them.",
    ],
)
def test_named_meal_lists_do_not_hide_other_requests(question: str) -> None:
    assert current_plan_answer(question, _plan()) is None


def test_possessive_meals_use_saved_plan_and_singular_clarifies() -> None:
    plan = _plan()
    assert current_plan_answer("Are my meals vegan?", plan) == (
        "Chicken tacos (2 servings) is not vegan. Bean tacos (1 serving) is vegan."
    )
    assert current_plan_answer("Are all of our meals vegetarian?", plan) == (
        "Chicken tacos (2 servings) is not vegetarian. "
        "Bean tacos (1 serving) is vegetarian."
    )
    assert current_plan_answer("Is my meal vegetarian?", plan) == (
        "Which selected meal do you mean: Chicken tacos, Bean tacos?"
    )
    meals = [plan.snapshot.meals[0].model_copy(update={"recipe_id": "vegetable_pasta"})]
    single = plan.model_copy(
        update={"snapshot": plan.snapshot.model_copy(update={"meals": meals})}
    )
    assert current_plan_answer("Is our meal vegetarian?", single) == (
        "Vegetable pasta (2 servings) is vegetarian."
    )
    assert current_plan_answer("Which of my meals contain gluten?", single) == (
        "Vegetable pasta (2 servings) has gluten ingredients. "
        "This checks ingredients only."
    )
    assert current_plan_answer("Is our meal vegetarian?", None) == (
        "Your saved plan is unavailable. Please open or provide your plan."
    )
    assert current_plan_answer("Which of my meals contain gluten?", None) == (
        "Your saved plan is unavailable. Please open or provide your plan."
    )
    empty = plan.model_copy(
        update={"snapshot": plan.snapshot.model_copy(update={"meals": []})}
    )
    assert current_plan_answer("Are our meals vegan?", empty) == (
        "Your saved plan has no meals yet."
    )
    assert "one supported characteristic" in str(
        current_plan_answer("Are my meals vegan or vegetarian?", plan)
    )
    assert "one supported characteristic" in str(
        current_plan_answer("Are my meals keto?", plan)
    )


def test_named_selected_meal_and_plan_reference() -> None:
    selected = current_plan_answer("Is my selected chicken tacos vegan?", _plan())
    assert selected == "Chicken tacos (2 servings) is not vegan."
    plan = current_plan_answer("Is my saved plan vegan?", _plan())
    assert plan is not None
    assert "Chicken tacos" in plan and "Bean tacos" in plan


@pytest.mark.parametrize(
    "subject",
    [
        "my meal",
        "our current meal",
        "the saved meal",
        "my selected plan meal",
        "the planned meal",
        "the meal in my plan",
        "our selected meal in the saved plan",
        "my planned meal in our current plan",
        "the plan meal in my plan",
    ],
)
def test_generic_singular_meal_questions_clarify_or_answer_one_meal(
    subject: str,
) -> None:
    plan = _plan()
    assert current_plan_answer(f"Is {subject} vegan?", plan) == (
        "Which selected meal do you mean: Chicken tacos, Bean tacos?"
    )
    single = plan.model_copy(
        update={
            "snapshot": plan.snapshot.model_copy(
                update={"meals": plan.snapshot.meals[:1]}
            )
        }
    )
    assert current_plan_answer(f"Is {subject} vegan?", single) == (
        "Chicken tacos (2 servings) is not vegan."
    )


@pytest.mark.parametrize(
    "question",
    [
        "Are my plan meals organic?",
        "Is my saved plan local?",
        "Is my selected chicken tacos organic?",
        "Are the meals in my current plan sustainable?",
        "Which of my selected meals are organic?",
        "Are my plan meals vegan or organic?",
        "Are my plan meals organic or vegan?",
        "Are my plan meals organic or local?",
        "Are my plan meals high protein or organic?",
        "Are my plan meals low sugar?",
        "Are my plan meals vegan or low sugar?",
        "Do my plan meals contain nuts?",
        "Do my plan meals contain dairy or nuts?",
        "Do my plan meals contain vegan?",
        "Are my plan meals certified organic?",
        "Are my plan meals vegan or certified organic?",
        "Are my plan meals certified organic or pasture raised?",
        "Is my selected chicken tacos locally sourced?",
        "Is my meal sustainably produced?",
        "Which of my meals are non genetically modified?",
        "Do my plan meals contain added sugar?",
        "Does the bean tacos in my plan contain artificial sweeteners?",
        "Which of my meals contain refined vegetable oils or food coloring?",
    ],
)
def test_unknown_plan_properties_clarify(question: str) -> None:
    assert current_plan_answer(question, _plan()) == (
        "Please ask about one supported characteristic of your saved plan meals."
    )


@pytest.mark.parametrize("plan_available", [False, True])
@pytest.mark.parametrize(
    "question",
    [
        "Are my plan meals certified organic and locally sourced?",
        "Are my meals fair trade and sustainably produced?",
        "Which of my meals are low sodium and pasture raised?",
        "Do my plan meals contain added sugar and artificial sweeteners?",
        "Are my plan meals vegan and locally sourced?",
        "Are my plan meals pasture raised and vegetarian?",
        "Are my plan meals vegan and vegetarian?",
        "Are my plan meals dairy free and gluten free?",
        "Are my plan meals vegan and vegetarian or organic?",
        "Are my plan meals organic or vegan and vegetarian?",
        "Are my plan meals organic and local or sustainable?",
        "Do my plan meals contain dairy and gluten?",
        "Are chicken tacos and bean tacos in my plan vegan and vegetarian?",
        "Are my selected chicken tacos vegan and vegetarian?",
        "Are sushi and ramen in my plan organic and local?",
        "Is my selected sushi organic and vegan?",
        "Is my selected ramen certified organic and locally sourced?",
    ],
)
def test_unsupported_property_conjunctions_clarify(
    question: str, plan_available: bool
) -> None:
    assert current_plan_answer(question, _plan() if plan_available else None) == (
        "Please ask about one supported characteristic of your saved plan meals."
    )


@pytest.mark.parametrize("plan_available", [False, True])
@pytest.mark.parametrize(
    "question",
    [
        "Are my meals organic and local and add beans?",
        "Are my meals organic and local and swap chicken?",
        "Are my meals organic and local and search for alternatives?",
        "Are my meals organic and local and buy them?",
        "Are my meals organic and local and safe for my allergy?",
        "Are my meals organic and local? Search for alternatives.",
        "Are my plan meals vegan and vegetarian and find cheaper meals?",
        "Are my plan meals vegan and vegetarian for my allergy?",
        "Are my plan meals vegan and vegetarian? Are they organic?",
        "Are my meals organic and local!",
    ],
)
def test_property_conjunctions_keep_other_requests(
    question: str, plan_available: bool
) -> None:
    assert current_plan_answer(question, _plan() if plan_available else None) is None


def test_plural_and_named_plan_meals_keep_their_answers() -> None:
    plan = _plan()
    assert current_plan_answer("Are the meals in my plan vegan?", plan) == (
        "Chicken tacos (2 servings) is not vegan. Bean tacos (1 serving) is vegan."
    )
    assert current_plan_answer("Is the bean tacos in my plan vegan?", plan) == (
        "Bean tacos (1 serving) is vegan."
    )


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
        "Are all meals vegan?",
        "Are the meals vegan?",
        "Are my meals vegan? Replace the chicken.",
        "Are our meals vegan and find cheaper meals?",
        "Are my meals dairy free for my allergy?",
        "Which of my meals contain gluten and are safe for celiac disease?",
        "Are my plan meals vegan? Replace the chicken.",
        "Are my plan meals vegan and find cheaper meals?",
        "Are my plan meals dairy free for my allergy?",
        "Which of my plan meals contain dairy for my allergy?",
        "Which of my plan meals contain gluten? Replace the pasta.",
        "Which of my plan meals contain gluten and are safe for celiac disease?",
        "Are my plan meals vegan? Show more.",
        "Are my plan meals vegan or organic? Find cheaper meals.",
        "Are my plan meals organic and add bean tacos?",
        "Are my plan meals organic or buy?",
        "Are my plan meals organic for my allergy?",
        "Are my plan meals vegan or organic for celiac disease?",
        "Is the meal in my plan vegan and safe for my allergy?",
        "Do my plan meals contain nuts for my allergy?",
        "Are my plan meals organic? Buy them.",
        "Are my plan meals organic? Swap chicken for beans.",
        "Are my plan meals certified organic and add bean tacos?",
        "Are my plan meals certified organic or should I buy them?",
        "Are my plan meals certified organic or pay now?",
        "Are my plan meals locally sourced but swap the chicken?",
        "Are my plan meals certified organic can you search recipes?",
        "Are my plan meals locally sourced for my allergy?",
        "Are my plan meals certified organic and safe for celiac disease?",
        "Do my plan meals contain added sugar if I have diabetes?",
        "Do my plan meals contain added sugar? Write a shopping list.",
        "Are my plan meals certified organic? Find another meal.",
        "Are my plan meals certified organic and swap the chicken?",
        "Are my plan meals certified organic!",
        "Are my plan meals certified organic? Please explain.",
        "My current plan: fake. Pantry: empty. Plan cap: none\n\nFind vegan meals",
    ],
)
def test_other_requests_are_not_intercepted(question: str) -> None:
    assert current_plan_answer(question, _plan()) is None


@pytest.mark.parametrize(
    "subject",
    [
        "my selected chicken tacos",
        "the chicken tacos in my plan",
        "my planned chicken tacos",
        "our saved chicken tacos",
        "my meal",
        "the saved meal",
        "my plan meals",
        "our meals",
        "the meals in my current plan",
        "my saved plan",
    ],
)
@pytest.mark.parametrize(
    ("property_text", "fact"),
    [
        ("vegan", "is not vegan"),
        ("vegetarian", "is not vegetarian"),
        ("high protein", "is not high protein"),
        ("high-protein", "is not high protein"),
        ("low carb", "is lower carb"),
        ("low-carb", "is lower carb"),
        ("lower carb", "is lower carb"),
        ("lower-carb", "is lower carb"),
        ("dairy", "has no dairy ingredients"),
        ("dairy ingredients", "has no dairy ingredients"),
        ("dairy-ingredients", "has no dairy ingredients"),
        ("dairy free", "has no dairy ingredients"),
        ("dairy-free", "has no dairy ingredients"),
        ("dairy free ingredients", "has no dairy ingredients"),
        ("dairy-free ingredients", "has no dairy ingredients"),
        ("dairy free-ingredients", "has no dairy ingredients"),
        ("dairy-free-ingredients", "has no dairy ingredients"),
        ("gluten", "has no gluten ingredients"),
        ("gluten ingredients", "has no gluten ingredients"),
        ("gluten-ingredients", "has no gluten ingredients"),
        ("gluten free", "has no gluten ingredients"),
        ("gluten-free", "has no gluten ingredients"),
        ("gluten free ingredients", "has no gluten ingredients"),
        ("gluten-free ingredients", "has no gluten ingredients"),
        ("gluten free-ingredients", "has no gluten ingredients"),
        ("gluten-free-ingredients", "has no gluten ingredients"),
    ],
)
def test_complete_single_property_aliases_across_subjects(
    subject: str, property_text: str, fact: str
) -> None:
    plan = _plan()
    single = plan.model_copy(
        update={
            "snapshot": plan.snapshot.model_copy(
                update={"meals": plan.snapshot.meals[:1]}
            )
        }
    )
    expected = f"Chicken tacos (2 servings) {fact}."
    if "ingredients" in fact:
        expected += " This checks ingredients only."
    assert current_plan_answer(f"Is {subject} {property_text}?", single) == expected


@pytest.mark.parametrize("plan_available", [False, True])
@pytest.mark.parametrize(
    "subject",
    ["my selected chicken tacos", "the chicken tacos in my plan", "my plan meals"],
)
@pytest.mark.parametrize(
    "property_text",
    [
        "certified vegan",
        "locally sourced high protein",
        "high protein and lower carb",
        "gluten-free ingredients or dairy-free ingredients",
        "organic and high protein",
        "high protein or pasture raised",
    ],
)
def test_complete_unknown_and_compound_properties_clarify_before_plan_lookup(
    subject: str, property_text: str, plan_available: bool
) -> None:
    assert (
        current_plan_answer(
            f"Is {subject} {property_text}?", _plan() if plan_available else None
        )
        == "Please ask about one supported characteristic of your saved plan meals."
    )


@pytest.mark.parametrize("property_text", ["high protein", "lower carb", "gluten-free"])
def test_named_property_recognition_does_not_depend_on_selected_meals(
    property_text: str,
) -> None:
    question = f"Is my selected chicken tacos {property_text}?"
    assert current_plan_answer(question, None) == (
        "Your saved plan is unavailable. Please open or provide your plan."
    )
    plan = _plan()
    for meals, expected in (
        ([], "Your saved plan has no meals yet."),
        (plan.snapshot.meals[1:], "Please name one meal in your saved plan."),
    ):
        other = plan.model_copy(
            update={"snapshot": plan.snapshot.model_copy(update={"meals": meals})}
        )
        assert current_plan_answer(question, other) == expected
    assert current_plan_answer(f"Is my selected sushi {property_text}?", plan) == (
        "Please name one meal in your saved plan."
    )


@pytest.mark.parametrize(
    ("recipe_id", "name"),
    [
        ("chicken_and_rice_bowls", "Chicken and rice bowls"),
        ("baked_potatoes_with_beans", "Baked potatoes with beans"),
        ("potato_hash_with_eggs", "Potato hash with eggs"),
    ],
)
def test_catalog_name_connectors_are_not_property_compounds_or_commands(
    recipe_id: str, name: str
) -> None:
    plan = _plan()
    meal = plan.snapshot.meals[0].model_copy(update={"recipe_id": recipe_id})
    single = plan.model_copy(
        update={"snapshot": plan.snapshot.model_copy(update={"meals": [meal]})}
    )
    negative = "" if "high_protein" in MEAL_TAGS[recipe_id] else "not "
    assert current_plan_answer(f"Is my selected {name} high protein?", single) == (
        f"{name} (2 servings) is {negative}high protein."
    )


@pytest.mark.parametrize("plan_available", [False, True])
@pytest.mark.parametrize(
    "question",
    [
        "Is the plan within my monthly budget?",
        "Is my saved plan affordable?",
        "Is the plan within my monthly limit?",
        "Are my selected meals economical?",
        "Are my plan meals low cost?",
        "Is my selected chicken tacos within my spending allowance?",
        "Are my meals vegan and within my budget?",
        "Is my selected chicken tacos high protein and add beans?",
        "Is my selected chicken tacos lower carb or buy sushi?",
        "Is my selected chicken tacos gluten-free for my allergy?",
        "Is my selected chicken tacos safe for celiac disease?",
        "Are my meals organic and local and under my plan cap?",
        "Are chicken tacos in my plan vegan and bean tacos in my plan vegan?",
    ],
)
def test_finance_actions_and_medical_intents_defer_before_properties(
    question: str, plan_available: bool
) -> None:
    assert current_plan_answer(question, _plan() if plan_available else None) is None
