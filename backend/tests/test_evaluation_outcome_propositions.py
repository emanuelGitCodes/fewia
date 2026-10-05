from collections import UserDict
from types import MappingProxyType

import pytest

from app.domain.catalog import INGREDIENTS, RECIPES
from app.evaluation_outcome_propositions import mapping, public_tags

_FIXED_PROPOSITIONS: tuple[tuple[str, str], ...] = (
    ("eggs are not vegan", "egg_conflict"),
    ("breakfast burritos contain eggs and are not vegan", "egg_conflict"),
    ("chicken is not vegan", "diet_conflict"),
    ("chicken are not vegan", "diet_conflict"),
    ("chicken tacos is not vegan", "diet_conflict"),
    ("chicken tacos are not vegan", "diet_conflict"),
    ("that recipe is not in the catalog", "unsupported"),
    ("salmon tacos are not supported", "unsupported"),
    (
        "i cannot map the named restrictions to catalog ingredients",
        "unknown",
    ),
    ("which catalog ingredients should i exclude", "restriction_question"),
    ("i cannot provide credentials or raw bank records", "secret_refusal"),
    ("i cannot buy items or place orders", "reject_purchase"),
    ("i cannot open external links or place orders", "reject_url"),
    ("i can help plan meals using the budget summary", "help"),
    ("i can help prepare a grocery plan", "help"),
    ("change the recipe or the restriction", "change"),
    (
        "which meal should i plan, and what servings, restrictions, "
        "and pantry items apply",
        "question",
    ),
)
_CATALOG_CHOICES: tuple[tuple[str, bool], ...] = tuple(
    (
        recipe.id.replace("_", " "),
        all(INGREDIENTS[key].vegan for key, _ in recipe.ingredients),
    )
    for recipe in RECIPES.values()
)


@pytest.mark.parametrize("answer,tag", _FIXED_PROPOSITIONS)
@pytest.mark.parametrize("suffix", ["", ".", "!", "?", "...?!"])
@pytest.mark.parametrize("uppercase", [False, True])
def test_fixed_propositions(
    answer: str, tag: str, suffix: str, uppercase: bool
) -> None:
    text = answer.upper() if uppercase else answer
    assert public_tags(f" \n{text}{suffix}\t", vegan=True) == {tag}


def test_multiple_supported_clauses_collect_tags() -> None:
    answer = ". ".join(text for text, _ in _FIXED_PROPOSITIONS)
    expected = {tag for _, tag in _FIXED_PROPOSITIONS}
    assert public_tags(answer, vegan=False) == expected


@pytest.mark.parametrize("name,is_vegan", _CATALOG_CHOICES)
@pytest.mark.parametrize("vegan", [False, True])
@pytest.mark.parametrize(
    "template,tag",
    [
        ("examples: {name}", "choice"),
        ("supported choices: {name}", "choice"),
        ("would you like {name} instead", "choice_question"),
    ],
)
def test_catalog_choices(
    name: str, is_vegan: bool, vegan: bool, template: str, tag: str
) -> None:
    answer = template.format(name=name).upper() + "?!"
    expected = None if vegan and not is_vegan else {tag}
    assert public_tags(answer, vegan=vegan) == expected


@pytest.mark.parametrize("vegan", [False, True])
@pytest.mark.parametrize("prefix", ["examples", "supported choices"])
def test_catalog_choice_lists(vegan: bool, prefix: str) -> None:
    names = [name for name, is_vegan in _CATALOG_CHOICES if not vegan or is_vegan]
    assert names
    answer = f"{prefix}: {', '.join(names)}."
    assert public_tags(answer, vegan=vegan) == {"choice"}


def test_vegan_choice_list_rejects_one_nonvegan_recipe() -> None:
    vegan_names = [name for name, is_vegan in _CATALOG_CHOICES if is_vegan]
    nonvegan_names = [name for name, is_vegan in _CATALOG_CHOICES if not is_vegan]
    assert vegan_names and nonvegan_names
    answer = f"supported choices: {vegan_names[0]}, {nonvegan_names[0]}"
    assert public_tags(answer, vegan=True) is None
    assert public_tags(answer, vegan=False) == {"choice"}


@pytest.mark.parametrize(
    "answer",
    [
        None,
        42,
        False,
        {},
        [],
        b"eggs are not vegan",
        "",
        " \n\t ",
        ".!?",
        "Can you clarify?",
        "What do you mean?",
        "I can help.",
        "Sure!",
        "examples: moon stew",
        "supported choices: moon stew",
        "would you like moon stew instead?",
        "eggs are not vegan because I say so",
        "eggs are not vegan; change the recipe or the restriction",
        "please change the recipe or the restriction",
        "eggs are not vegan, and I can help prepare a grocery plan",
    ],
)
def test_unsupported_or_malformed_answers(answer: object) -> None:
    assert public_tags(answer, vegan=False) is None


@pytest.mark.parametrize("text,_tag", _FIXED_PROPOSITIONS)
@pytest.mark.parametrize("unknown_first", [False, True])
def test_unknown_clause_invalidates_supported_answer(
    text: str, _tag: str, unknown_first: bool
) -> None:
    clauses = ["Everything is guaranteed safe", text]
    if not unknown_first:
        clauses.reverse()
    assert public_tags(". ".join(clauses), vegan=False) is None


def test_catalog_choice_with_unknown_extra_wording() -> None:
    name = _CATALOG_CHOICES[0][0]
    for answer in (
        f"examples: {name}, moon stew",
        f"examples: {name},",
        f"would you like {name} instead with guaranteed allergy safety",
        f"examples: {name}. Everything is guaranteed safe.",
    ):
        assert public_tags(answer, vegan=False) is None


@pytest.mark.parametrize(
    "value",
    [
        {"role": "user", "count": 1},
        UserDict({"role": "user", "count": 1}),
        MappingProxyType({"role": "user", "count": 1}),
    ],
)
def test_mapping_accepts_string_keys(value: object) -> None:
    assert mapping(value) == {"role": "user", "count": 1}


@pytest.mark.parametrize(
    "value",
    [None, 42, False, "text", [], [("role", "user")], {1: "user"}, {"role": 1, 2: 3}],
)
def test_mapping_rejects_nonmappings_and_nonstring_keys(value: object) -> None:
    assert mapping(value) == {}


def test_mapping_preserves_nested_values_and_input() -> None:
    nested: dict[str, object] = {"answer": "eggs are not vegan"}
    original: dict[str, object] = {"result": nested}
    result = mapping(original)
    assert result["result"] is nested
    assert original == {"result": {"answer": "eggs are not vegan"}}
    assert mapping({}) == {}
