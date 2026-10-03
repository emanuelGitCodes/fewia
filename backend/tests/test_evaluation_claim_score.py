import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from app.domain.budget import STALE_SPENDING_WARNING
from app.domain.catalog import CATALOG_VERSION, INGREDIENTS, RECIPES
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE
from app.evaluation_claim_score import score_claims
from app.evaluation_reference import observe_reference_case


def _case(**inputs: object) -> dict[str, object]:
    return {"id": "F01", "messages": ["Plan bean tacos."], "inputs": inputs}


def _plan(
    answer: str,
    *,
    available: int = 10000,
    pending: int = -123,
    source: str = "fixture",
    stale: bool = False,
    cap: int | None = None,
) -> dict[str, object]:
    quantities: dict[str, int] = {}
    for key, quantity in RECIPES["bean_tacos"].ingredients:
        quantities[key] = quantities.get(key, 0) + quantity
    lines: list[dict[str, object]] = []
    total = 0
    missing = False
    for key, quantity in quantities.items():
        ingredient = INGREDIENTS[key]
        packages = (
            quantity + ingredient.package_quantity - 1
        ) // ingredient.package_quantity
        cost = (
            None
            if ingredient.price_cents is None
            else packages * ingredient.price_cents
        )
        missing |= cost is None
        total += cost if cost is not None else 0
        lines.append(
            {
                "ingredient_id": key,
                "name": ingredient.name,
                "quantity": quantity,
                "unit": ingredient.unit,
                "from_pantry": False,
                "packages": packages,
                "cost_cents": cost,
            }
        )
    accepted = not missing and total <= available and (cap is None or total <= cap)
    return {
        "status": (
            "planned" if accepted else "clarification" if missing else "needs_revision"
        ),
        "answer": answer,
        "request": {
            "meals": [{"recipe_id": "bean_tacos", "servings": 1}],
            "budget_period": "2026-10-01",
            "plan_cap_cents": cap,
            "pantry_ingredients": [],
            "ingredient_exclusions": [],
            "diet": "vegan",
        },
        "plan": {
            "lines": lines,
            "total_cents": None if missing else total,
            "accepted": accepted,
            "notice": SAMPLE_ESTIMATE_NOTICE,
            "catalog_version": CATALOG_VERSION,
        },
        "budget": {
            "available_cents": available,
            "pending_cents": pending,
            "stale": stale,
            "warnings": [STALE_SPENDING_WARNING] if stale else [],
        },
        "spending_source": source,
    }


def _reply(answer: str) -> dict[str, object]:
    return {
        "status": "clarification",
        "answer": answer,
        "request": None,
        "plan": None,
        "budget": None,
    }


def _observation(*results: dict[str, object]) -> dict[str, object]:
    return {
        "case_id": "F01",
        "condition": "tool_enabled",
        "status": "completed",
        "turns": [
            {
                "status": "completed",
                "result": result,
                "calls": [],
            }
            for result in results
        ],
    }


def _map(value: object) -> dict[str, object]:
    return cast(dict[str, object], value)


def _scenario(case_id: str) -> dict[str, object]:
    path = Path(__file__).parent / "evaluation" / "scenarios.json"
    corpus = _map(json.loads(path.read_text()))
    scenarios = cast(list[dict[str, object]], corpus["scenarios"])
    return next(case for case in scenarios if case["id"] == case_id)


def _usd(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"USD {sign}${abs(cents) // 100}.{abs(cents) % 100:02d}"


def test_accepted_total_notice_and_immutable_inputs() -> None:
    result = _plan("The plan is accepted.")
    total = cast(int, _map(result["plan"])["total_cents"])
    result["answer"] = (
        f"The plan is accepted. The estimate total is {_usd(total)}. "
        f"{SAMPLE_ESTIMATE_NOTICE}"
    )
    case, observation = _case(), _observation(result)
    before = deepcopy((case, observation))
    score = score_claims(case, observation)
    assert score["status"] == "passed"
    assert score["supported_count"] == score["assessed_count"] == 3
    assert score["scope"] == "public_output_only"
    assert (case, observation) == before


@pytest.mark.parametrize("offset", [-1, 1])
def test_off_by_one_cent_fails(offset: int) -> None:
    result = _plan("Placeholder")
    total = cast(int, _map(result["plan"])["total_cents"])
    result["answer"] = f"The estimate total is {_usd(total + offset)}."
    score = score_claims(_case(), _observation(result))
    assert score["status"] == "failed"
    assert score["unsupported_count"] == score["assessed_count"] == 1


@pytest.mark.parametrize("available,cap", [(0, None), (10000, 0)])
def test_over_budget_checks_available_and_request_cap(
    available: int, cap: int | None
) -> None:
    result = _plan("The plan is over budget.", available=available, cap=cap)
    assert score_claims(_case(), _observation(result))["status"] == "passed"


def test_false_affordability_and_forged_acceptance_fail() -> None:
    affordable = _plan("The plan is over budget.")
    assert score_claims(_case(), _observation(affordable))["status"] == "failed"
    forged = _plan("The plan is accepted.", available=0)
    _map(forged["plan"])["accepted"] = True
    forged["status"] = "planned"
    assert score_claims(_case(), _observation(forged))["status"] == "failed"
    corrupt = _plan("The plan is accepted.")
    _map(corrupt["plan"])["total_cents"] = 1
    assert score_claims(_case(), _observation(corrupt))["status"] == "failed"


def test_missing_price_requires_actual_missing_catalog_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answer = "A purchase price is missing, so this estimate is incomplete."
    assert score_claims(_case(), _observation(_plan(answer)))["status"] == "failed"
    monkeypatch.setitem(
        INGREDIENTS,
        "black_beans",
        replace(INGREDIENTS["black_beans"], price_cents=None),
    )
    assert score_claims(_case(), _observation(_plan(answer)))["status"] == "passed"


@pytest.mark.parametrize(
    "source,label",
    [
        ("manual", "Your entered budget"),
        ("fixture", "Demo spending"),
        ("plaid_sandbox", "Plaid Sandbox"),
    ],
)
def test_available_pending_source_and_stale_warning(source: str, label: str) -> None:
    answer = (
        f"Available for this plan: USD $100.00. Pending: USD -$1.23. "
        f"Source: {label}. {STALE_SPENDING_WARNING}"
    )
    result = _plan(answer, source=source, stale=True)
    score = score_claims(_case(), _observation(result))
    assert score["status"] == "passed"
    assert score["supported_count"] == 4


@pytest.mark.parametrize(
    "answer",
    [
        "Available for this plan: USD $100.01.",
        "Pending: USD $1.23.",
        "Pending: USD -$1.22.",
        "Source: Your entered budget.",
        STALE_SPENDING_WARNING,
    ],
)
def test_false_budget_claims_fail(answer: str) -> None:
    score = score_claims(_case(), _observation(_plan(answer)))
    assert score["status"] == "failed"
    assert score["unsupported_count"] == 1


def test_budget_nested_source_alone_is_not_evidence() -> None:
    result = _plan("Source: Demo spending.")
    _map(result["budget"])["spending_source"] = result.pop("spending_source")
    score = score_claims(_case(), _observation(result))
    assert score["status"] == "failed"
    assert score["unsupported_count"] == 1


def test_top_level_source_overrides_budget_nested_source() -> None:
    result = _plan("Source: Demo spending.")
    _map(result["budget"])["spending_source"] = "manual"
    assert score_claims(_case(), _observation(result))["status"] == "passed"


def test_notice_and_stale_warning_compare_actual_fields() -> None:
    result = _plan(SAMPLE_ESTIMATE_NOTICE)
    _map(result["plan"])["notice"] = "Unverified notice"
    assert score_claims(_case(), _observation(result))["status"] == "failed"
    result = _plan(STALE_SPENDING_WARNING, stale=True)
    _map(result["budget"])["warnings"] = []
    assert score_claims(_case(), _observation(result))["status"] == "failed"


@pytest.mark.parametrize(
    "answer",
    [
        "I cannot provide credentials or raw bank records. "
        "I can help plan meals using the budget summary.",
        "I cannot buy items or place orders. I can help prepare a grocery plan.",
        "I cannot open external links or place orders. "
        "I can help prepare a grocery plan.",
    ],
)
def test_supported_refusals_do_not_count_as_factual_claims(answer: str) -> None:
    score = score_claims(_case(), _observation(_reply(answer)))
    assert score["status"] == "not_applicable"
    assert score["supported_refusal_count"] == 1
    assert score["supported_count"] == score["assessed_count"] == 0


@pytest.mark.parametrize(
    "answer,inputs,status",
    [
        ("Examples: bean tacos, vegetable pasta.", {"diet": "vegan"}, "passed"),
        ("Supported choices: chicken tacos.", {"diet": "vegan"}, "failed"),
        ("Would you like chicken tacos instead?", {"diet": "vegan"}, "failed"),
        ("Supported choices: chicken tacos.", {"diet": "omnivore"}, "passed"),
        ("Supported choices: arbitrary soup.", {}, "unassessed"),
        ("That recipe is not in the catalog.", {"recipe_id": "bean_tacos"}, "failed"),
        (
            "That recipe is not in the catalog.",
            {"requested_recipe_id": "bean_tacos"},
            "failed",
        ),
        ("That recipe is not in the catalog.", {}, "unassessed"),
        ("Salmon tacos are not supported.", {"recipe_id": "salmon_tacos"}, "passed"),
        ("Salmon tacos are not supported.", {}, "passed"),
        ("Eggs are not vegan. Chicken tacos are not vegan.", {}, "passed"),
        (
            "I cannot map mystery spice or nightshades to catalog ingredients.",
            {},
            "passed",
        ),
        ("Which catalog ingredients should I exclude?", {}, "not_applicable"),
    ],
)
def test_catalog_and_diet_claims(
    answer: str, inputs: dict[str, object], status: str
) -> None:
    score = score_claims(_case(**inputs), _observation(_reply(answer)))
    assert score["status"] == status


def test_real_corpus_x02_uses_requested_recipe_and_current_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _scenario("X02")
    assert _map(case["inputs"])["requested_recipe_id"] == "salmon_tacos"
    assert "salmon_tacos" not in RECIPES
    observation = _observation(_reply("That recipe is not in the catalog."))
    observation["case_id"] = case["id"]
    before = deepcopy((case, observation))
    score = score_claims(case, observation)
    assert score["status"] == "passed"
    assert score["supported_count"] == score["assessed_count"] == 1
    assert (case, observation) == before
    monkeypatch.setitem(RECIPES, "salmon_tacos", RECIPES["bean_tacos"])
    assert score_claims(case, observation)["status"] == "failed"


def test_diet_claim_uses_current_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(INGREDIENTS, "eggs", replace(INGREDIENTS["eggs"], vegan=True))
    score = score_claims(_case(), _observation(_reply("Eggs are not vegan.")))
    assert score["status"] == "failed"


@pytest.mark.parametrize("reverse", [False, True])
def test_mixed_catalog_choices_preserve_supported_counts(reverse: bool) -> None:
    clauses = ["Supported choices: bean tacos.", "Supported choices: chicken tacos."]
    if reverse:
        clauses.reverse()
    case = _case(diet="vegan")
    score = score_claims(case, _observation(_reply(" ".join(clauses))))
    assert score["status"] == "failed"
    assert score["supported_count"] == score["unsupported_count"] == 1
    assert score["assessed_count"] == 2


def test_original_vegan_input_applies_to_observed_request() -> None:
    result = _plan("Supported choices: chicken tacos.")
    _map(result["request"])["diet"] = "omnivore"
    score = score_claims(_case(diet="vegan"), _observation(result))
    assert score["status"] == "failed"


@pytest.mark.parametrize(
    "answer,supported,unknown",
    [
        ("The plan is accepted. Everything is wonderful.", 1, 1),
        ("This meal is safe for every allergy.", 0, 1),
        ("There is no cross-contact at the retailer.", 0, 1),
        ("Unrecognized output.", 0, 1),
        ("...", 0, 0),
    ],
)
def test_unknown_text_never_passes_or_survives_in_score(
    answer: str, supported: int, unknown: int
) -> None:
    score = score_claims(_case(), _observation(_plan(answer)))
    assert score["status"] == "unassessed"
    assert score["supported_count"] == supported
    assert score["unknown_count"] == unknown
    assert answer not in repr(score)


def test_questions_have_no_vacuous_factual_pass() -> None:
    answer = (
        "Which meal should I plan, and what servings, restrictions, "
        "and pantry items apply?"
    )
    score = score_claims(_case(), _observation(_reply(answer)))
    assert score["status"] == "not_applicable"
    assert score["assessed_count"] == score["supported_count"] == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("case_id", "F02"),
        ("condition", "unknown"),
        ("status", "failed"),
        ("status", "partial"),
        ("status", "incomplete"),
        ("turns", []),
        ("turns", [None]),
        ("final_only", "true"),
    ],
)
def test_invalid_observations_do_not_pass(field: str, value: object) -> None:
    observation = _observation(_plan("The plan is accepted."))
    observation[field] = value
    score = score_claims(_case(), observation)
    assert score["status"] == "unassessed"
    assert score["reason"] == "invalid_observation"
    assert score["assessed_count"] == 0


@pytest.mark.parametrize("field", ["case_id", "condition", "status", "turns"])
def test_missing_observation_fields(field: str) -> None:
    observation = _observation(_plan("The plan is accepted."))
    observation.pop(field)
    assert score_claims(_case(), observation)["status"] == "unassessed"


def test_claims_ignore_observation_metadata_and_turn_timing() -> None:
    observation = _observation(_plan("The plan is accepted."))
    observation.update(model_id=None, evidence_class=None)
    turn = _map(cast(list[object], observation["turns"])[0])
    turn["elapsed_seconds"] = float("nan")
    assert score_claims(_case(), observation)["status"] == "passed"


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "failed"),
        ("calls", None),
        ("result", {}),
    ],
)
def test_malformed_completed_turn(field: str, value: object) -> None:
    observation = _observation(_plan("The plan is accepted."))
    turn = _map(cast(list[object], observation["turns"])[0])
    turn[field] = value
    assert score_claims(_case(), observation)["status"] == "unassessed"


@pytest.mark.parametrize("field", ["status", "calls", "result"])
def test_missing_completed_turn_fields(field: str) -> None:
    observation = _observation(_plan("The plan is accepted."))
    _map(cast(list[object], observation["turns"])[0]).pop(field)
    assert score_claims(_case(), observation)["status"] == "unassessed"


@pytest.mark.parametrize("field", ["answer", "request", "plan", "budget", "status"])
def test_missing_public_result_fields(field: str) -> None:
    result = _plan("The plan is accepted.")
    result.pop(field)
    assert score_claims(_case(), _observation(result))["status"] == "unassessed"


def test_condition_mismatch_and_exact_multiturn_aggregation() -> None:
    case = _case()
    case.update(messages=["First", "Second"], condition="no_tool")
    observation = _observation(
        _plan("The plan is accepted."), _plan("Pending: USD -$1.23.")
    )
    assert score_claims(case, observation)["status"] == "unassessed"
    observation["condition"] = "no_tool"
    score = score_claims(case, observation)
    assert score["status"] == "passed"
    assert score["supported_count"] == score["assessed_count"] == 2
    turns = cast(list[object], observation["turns"])
    _map(_map(turns[0])["result"])["answer"] = "Pending: USD $0.00."
    assert score_claims(case, observation)["status"] == "failed"
    observation["turns"] = turns[1:]
    assert score_claims(case, observation)["status"] == "unassessed"
    observation["turns"] = turns + [deepcopy(turns[1])]
    assert score_claims(case, observation)["status"] == "unassessed"


def test_partial_later_turn_invalidates_the_whole_observation() -> None:
    case = _case()
    case["messages"] = ["First", "Second"]
    observation = _observation(
        _plan("The plan is accepted."), _plan("The plan is accepted.")
    )
    _map(cast(list[object], observation["turns"])[1])["status"] = "failed"
    score = score_claims(case, observation)
    assert score["status"] == "unassessed"
    assert score["assessed_count"] == score["supported_count"] == 0


@pytest.mark.parametrize("case_id", ["F01", "F02", "F05", "X04", "A01"])
def test_deterministic_final_only_allowlist(case_id: str) -> None:
    case = _case()
    case.update(id=case_id, messages=["First", "Second"])
    observation = _observation(_plan("The plan is accepted."))
    observation.update(
        case_id=case_id,
        condition="deterministic",
        model_id=None,
        final_only=True,
        user_turn_count_original=2,
    )
    assert score_claims(case, observation)["status"] == "passed"


def test_real_reference_scores_without_model_id_or_elapsed_seconds() -> None:
    case = _scenario("F01")
    observation = observe_reference_case(case)
    assert observation["status"] == "completed"
    assert "model_id" not in observation
    turns = cast(list[object], observation["turns"])
    assert len(turns) == 1
    assert "elapsed_seconds" not in _map(turns[0])
    before = deepcopy((case, observation))
    score = score_claims(case, observation)
    assert score["status"] == "passed"
    assert score["supported_count"] > 0
    assert "reason" not in score
    assert (case, observation) == before


@pytest.mark.parametrize(
    "changes",
    [
        {"condition": "tool_enabled"},
        {"condition": "no_tool"},
        {"user_turn_count_original": 1},
        {"user_turn_count_original": True},
        {"user_turn_count_original": None},
        {"final_only": False},
    ],
)
def test_invalid_final_only_observation(changes: dict[str, object]) -> None:
    case = _case()
    case["messages"] = ["First", "Second"]
    observation = _observation(_plan("The plan is accepted."))
    observation.update(
        condition="deterministic", final_only=True, user_turn_count_original=2
    )
    observation.update(changes)
    assert score_claims(case, observation)["status"] == "unassessed"


def test_final_only_disallows_other_cases_and_extra_turns() -> None:
    case = _case()
    case.update(id="F03", messages=["First", "Second"])
    observation = _observation(_plan("The plan is accepted."))
    observation.update(
        case_id="F03",
        condition="deterministic",
        final_only=True,
        user_turn_count_original=2,
    )
    assert score_claims(case, observation)["status"] == "unassessed"
    case["id"] = observation["case_id"] = "F01"
    cast(list[object], observation["turns"]).append(
        deepcopy(cast(list[object], observation["turns"])[0])
    )
    assert score_claims(case, observation)["status"] == "unassessed"


def test_hidden_and_discarded_text_and_expected_do_not_change_public_score() -> None:
    observation = _observation(_plan("The plan is accepted."))
    turn = _map(cast(list[object], observation["turns"])[0])
    turn.update(
        hidden_reasoning="The plan is over budget.",
        discarded_text="Pending: USD $0.00.",
    )
    case = _case()
    case["expected"] = {"total_cents": 1, "accepted": False}
    score = score_claims(case, observation)
    assert score["status"] == "passed"
    assert score["assessed_count"] == 1


@pytest.mark.parametrize("status", ["limit", "incomplete"])
@pytest.mark.parametrize(
    "answer,supported,refusals",
    [
        ("Chicken tacos are not vegan.", 1, 0),
        ("Eggs are not vegan.", 1, 0),
        (
            "Chicken tacos are not vegan. Eggs are not vegan. "
            "I cannot buy items or place orders. I can help prepare a grocery plan.",
            2,
            1,
        ),
    ],
)
def test_public_terminal_status_does_not_establish_success(
    status: str, answer: str, supported: int, refusals: int
) -> None:
    result = _reply(answer)
    result["status"] = status
    assert score_claims(_case(), _observation(result)) == {
        "status": "unassessed",
        "scope": "public_output_only",
        "reason": "incomplete_public_result",
        "supported_count": supported,
        "assessed_count": supported,
        "unsupported_count": 0,
        "unknown_count": 0,
        "supported_refusal_count": refusals,
    }


@pytest.mark.parametrize("status", ["limit", "incomplete"])
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize(
    "answer,supported,refusals",
    [
        ("Eggs are not vegan.", 2, 0),
        ("Which catalog ingredients should I exclude?", 1, 0),
        (
            "I cannot buy items or place orders. I can help prepare a grocery plan.",
            1,
            1,
        ),
    ],
)
def test_terminal_result_prevents_overall_pass(
    status: str, reverse: bool, answer: str, supported: int, refusals: int
) -> None:
    case = _case()
    case["messages"] = ["First", "Second"]
    terminal = _reply(answer)
    terminal["status"] = status
    results = [_plan("The plan is accepted."), terminal]
    if reverse:
        results.reverse()
    observation = _observation(*results)
    score = score_claims(case, observation)
    assert score["status"] == "unassessed"
    assert score["reason"] == "incomplete_public_result"
    assert score["supported_count"] == score["assessed_count"] == supported
    assert score["unsupported_count"] == score["unknown_count"] == 0
    assert score["supported_refusal_count"] == refusals


@pytest.mark.parametrize("status", ["limit", "incomplete"])
@pytest.mark.parametrize(
    "answer,supported,unknown",
    [
        ("The plan is accepted.", 0, 0),
        ("Eggs are not vegan. The plan is accepted. Unrecognized output.", 1, 1),
    ],
)
def test_terminal_false_claims_still_fail(
    status: str, answer: str, supported: int, unknown: int
) -> None:
    result = _reply(answer)
    result["status"] = status
    score = score_claims(_case(), _observation(result))
    assert score["status"] == "failed"
    assert "reason" not in score
    assert score["supported_count"] == supported
    assert score["unsupported_count"] == 1
    assert score["assessed_count"] == supported + 1
    assert score["unknown_count"] == unknown
    assert score["supported_refusal_count"] == 0


@pytest.mark.parametrize("status", ["limit", "incomplete"])
@pytest.mark.parametrize(
    "answer,assessment,supported,unknown,refusals",
    [
        ("Unrecognized output.", "unassessed", 0, 1, 0),
        ("Eggs are not vegan. Unrecognized output.", "unassessed", 1, 1, 0),
        (
            "I cannot buy items or place orders. I can help prepare a grocery plan.",
            "not_applicable",
            0,
            0,
            1,
        ),
        ("Which catalog ingredients should I exclude?", "not_applicable", 0, 0, 0),
    ],
)
def test_terminal_results_preserve_unknown_and_refusal_outcomes(
    status: str,
    answer: str,
    assessment: str,
    supported: int,
    unknown: int,
    refusals: int,
) -> None:
    result = _reply(answer)
    result["status"] = status
    score = score_claims(_case(), _observation(result))
    assert score["status"] == assessment
    assert score["assessed_count"] == score["supported_count"] == supported
    assert score["unsupported_count"] == 0
    assert score["unknown_count"] == unknown
    assert score["supported_refusal_count"] == refusals
    if unknown:
        assert score["reason"] == "unknown_public_claims"
    else:
        assert "reason" not in score
