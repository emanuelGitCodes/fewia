"""Contract tests for the versioned grocery evaluation corpus."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import cast

from app.domain.catalog import CATALOG_VERSION
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE, SUPPORTED_RECIPE_IDS

CORPUS_PATH = Path(__file__).parent / "evaluation" / "scenarios.json"
VERSION = "grocery-eval-v1.1"
REPEATS = 3
MODE_NOTE = "Fixtures do not prove LLM quality or live providers."
NOTICE = (
    "Estimated from the demo price catalog. Store prices, availability, "
    "taxes, delivery fees, and tips are not verified."
)
GROUP_COUNTS = {
    "budget": 5,
    "meals": 7,
    "followup": 5,
    "missing": 4,
    "provider": 5,
    "adversarial": 4,
}
GROUP_IDS = {
    "budget": ("B01", "B02", "B03", "B04", "B05"),
    "meals": ("M01", "M02", "M03", "M04", "M05", "M06", "M07"),
    "followup": ("F01", "F02", "F03", "F04", "F05"),
    "missing": ("X01", "X02", "X03", "X04"),
    "provider": ("P01", "P02", "P03", "P04", "P05"),
    "adversarial": ("A01", "A02", "A03", "A04"),
}
REQUIRES_MODEL = frozenset(
    {
        "F01",
        "F02",
        "F04",
        "F05",
        "X02",
        "X03",
        "X04",
        "P04",
        "A01",
        "A02",
        "A03",
        "A04",
    }
)
MODEL_TOOL_NAME = "plan_groceries"
DOMAIN_CALL_NAMES = frozenset(
    {
        "calculate_budget",
        "plan_groceries",
        "sync_item",
        "create_job",
        "process_one",
        "prepare_handoff",
        "dispatch_handoff",
    }
)
JOB_KINDS = frozenset({"sync", "agent"})
EVIDENCE_TARGET_NOTE = (
    "Target evidence_class and path_classes labels are not observed proof."
)
FAKE_GUARD_NOTE = "Fake guards do not assess model quality."
METRICS_NOTE = "Metrics remain unassessed until executed."
UNSUPPORTED_RECIPE_IDS = frozenset({"salmon_tacos"})
SECRET_MARKER = "FIXTURE_SECRET_MARKER"
FORBIDDEN_SCORE_KEYS = frozenset(
    {
        "accuracy",
        "fake_score",
        "pass_rate",
        "success_rate",
        "success_score",
        "task_success",
    }
)
FORBIDDEN_LEAK_TOKENS = (
    "access_token",
    "api.plaid.com",
    "bedrock-runtime",
    "instacart.com",
    "akia",
    SECRET_MARKER.lower(),
)
PROVIDER_URL_TOKENS = ("amazonaws.com", "plaid.com", "instacart.com")
SCENARIO_KEYS = (
    "id",
    "group",
    "requires_model",
    "prompt",
    "messages",
    "inputs",
    "expected",
    "fixture_behavior",
)
EXPECTED_KEYS = (
    "domain_calls",
    "model_tools",
    "unnecessary_model_tools",
    "allowed_outcomes",
    "evidence_ids",
    "evidence_class",
    "path_classes",
    "constraint_results",
)
AMBIGUOUS_EXPECTED_KEYS = frozenset({"tools", "unnecessary_tools"})
EVIDENCE_CLASS_LABELS = (
    "deterministic_fake_provider",
    "local_postgresql",
    "plaid_sandbox",
    "live_instacart_development",
    "real_bedrock",
    "deployed_aws",
)
PATH_CLASSES = (
    "local_react_typescript_chat",
    "fastapi",
    "local_postgresql",
    "worker",
    "floci_sqs",
    "floci_s3",
    "real_bedrock",
    "plaid_sandbox",
    "live_instacart_development",
)
EVIDENCE_REQUIREMENTS = {
    "kind": "conditional_requirements",
    "owner_scoped": True,
    "hidden_reasoning": "forbidden",
    "fabricate_hashes": False,
    "imply_snapshots_created": False,
    "when_plan_returned": {
        "immutable_revision": True,
        "catalog_version": CATALOG_VERSION,
    },
}
INVENTED_EVIDENCE_ID_TOKENS = (
    "budget:user-",
    "spending:user-",
    "plan:user-",
    "job:user-",
    "handoff:user-",
    "catalog:sample-prices-v1",
    "catalog:sample-prices-v2",
)
MEAL_TOTALS = {
    "M01": 1703,
    "M02": 2860,
    "M03": 2647,
    "M04": 1414,
    "M05": 1475,
    "M06": 1853,
    "M07": 4341,
    "F01": 1574,
    "F02": 1703,
    "X04": 3471,
    "A01": 3471,
    "B03": 1703,
}


def load_corpus() -> dict[str, object]:
    payload: object = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return cast(dict[str, object], payload)


def as_object(value: object, name: str) -> dict[str, object]:
    assert isinstance(value, dict), name
    return cast(dict[str, object], value)


def as_list(value: object, name: str) -> list[object]:
    assert isinstance(value, list), name
    return cast(list[object], value)


def as_str(value: object, name: str) -> str:
    assert type(value) is str, name
    return value


def as_bool(value: object, name: str) -> bool:
    assert type(value) is bool, name
    return value


def as_int(value: object, name: str) -> int:
    assert type(value) is int, name
    return value


def call_names(rows: Sequence[object], field: str) -> list[str]:
    names: list[str] = []
    for item in rows:
        call = as_object(item, field)
        names.append(as_str(call["name"], "name"))
    return names


def scenarios(corpus: Mapping[str, object]) -> list[dict[str, object]]:
    rows = as_list(corpus["scenarios"], "scenarios")
    return [as_object(row, "scenario") for row in rows]


def walk(value: object) -> Iterator[object]:
    yield value
    if isinstance(value, dict):
        for nested in value.values():
            yield from walk(nested)
        return
    if isinstance(value, list):
        for nested in value:
            yield from walk(nested)


def text_blobs(value: object) -> list[str]:
    blobs: list[str] = []
    for item in walk(value):
        if type(item) is str:
            blobs.append(item)
    return blobs


def recipe_ids_from(value: object) -> set[str]:
    found: set[str] = set()
    for item in walk(value):
        if not isinstance(item, dict):
            continue
        row = cast(dict[str, object], item)
        recipe_id = row.get("recipe_id")
        if type(recipe_id) is str:
            found.add(recipe_id)
    requested = None
    if isinstance(value, dict):
        requested = value.get("requested_recipe_id")
        if type(requested) is str:
            found.add(requested)
    return found


def test_corpus_top_level_schema_is_versioned() -> None:
    corpus = load_corpus()
    assert corpus["version"] == VERSION
    assert corpus["catalog_version"] == CATALOG_VERSION
    assert corpus["catalog_version"] == "sample-prices-v2"
    assert corpus["repeats"] == REPEATS
    assert corpus["mode_note"] == MODE_NOTE
    assert corpus["evidence_target_note"] == EVIDENCE_TARGET_NOTE
    assert corpus["fake_guard_note"] == FAKE_GUARD_NOTE
    assert corpus["metrics_note"] == METRICS_NOTE
    assert corpus["metrics_status"] == "unassessed"
    assert corpus["estimate_notice"] == NOTICE
    assert corpus["estimate_notice"] == SAMPLE_ESTIMATE_NOTICE
    baseline = as_object(corpus["baseline"], "baseline")
    assert baseline["clock"] == "2026-09-06T16:00:00Z"
    assert baseline["budget_period"] == "2026-09-01"
    assert baseline["available_cents"] == 10000
    assert baseline["posted_cents"] == 0
    assert baseline["seed"] == 42
    assert baseline["max_model_turns"] == 8
    assert baseline["max_planner_revisions"] == 3
    assert "success_score" not in corpus
    metrics = as_list(corpus["metrics"], "metrics")
    assert "tool_selection" in metrics
    assert "p50_latency" in metrics
    assert "p95_latency" in metrics
    assert corpus["evidence_class_labels"] == list(EVIDENCE_CLASS_LABELS)
    assert corpus["path_classes"] == list(PATH_CLASSES)


def test_corpus_has_thirty_unique_scenarios_and_exact_groups() -> None:
    rows = scenarios(load_corpus())
    assert len(rows) == 30
    ids = [as_str(row["id"], "id") for row in rows]
    assert len(ids) == len(set(ids))
    groups = Counter(as_str(row["group"], "group") for row in rows)
    assert dict(groups) == GROUP_COUNTS
    by_group: dict[str, list[str]] = {name: [] for name in GROUP_IDS}
    for row in rows:
        by_group[as_str(row["group"], "group")].append(as_str(row["id"], "id"))
    for group, expected_ids in GROUP_IDS.items():
        assert tuple(by_group[group]) == expected_ids


def test_requires_model_flags_match_the_assignment() -> None:
    for row in scenarios(load_corpus()):
        scenario_id = as_str(row["id"], "id")
        required = as_bool(row["requires_model"], "requires_model")
        assert required is (scenario_id in REQUIRES_MODEL)


def test_model_tools_and_domain_calls_stay_separate() -> None:
    for row in scenarios(load_corpus()):
        scenario_id = as_str(row["id"], "id")
        required = as_bool(row["requires_model"], "requires_model")
        expected = as_object(row["expected"], "expected")
        domain_calls = as_list(expected["domain_calls"], "domain_calls")
        model_tools = as_list(expected["model_tools"], "model_tools")
        if required is False:
            assert model_tools == []
        for item in model_tools:
            tool = as_object(item, "model_tool")
            assert as_str(tool["name"], "name") == MODEL_TOOL_NAME
            assert "arguments" in tool
            assert "expectation" not in tool
            as_object(tool["arguments"], "arguments")
        for item in domain_calls:
            call = as_object(item, "domain_call")
            name = as_str(call["name"], "name")
            assert name in DOMAIN_CALL_NAMES
            assert "arguments" not in call
            expectation = as_object(call["expectation"], "expectation")
            if name == "create_job":
                assert as_str(expectation["kind"], "kind") in JOB_KINDS
        unnecessary = as_list(
            expected["unnecessary_model_tools"],
            "unnecessary_model_tools",
        )
        for name in unnecessary:
            assert type(name) is str
            assert name != MODEL_TOOL_NAME or scenario_id in {"X02", "X03"}


def test_scenario_schema_stores_domain_calls_model_tools_evidence_and_constraints() -> (
    None
):
    for row in scenarios(load_corpus()):
        for key in SCENARIO_KEYS:
            assert key in row
        expected = as_object(row["expected"], "expected")
        for key in EXPECTED_KEYS:
            assert key in expected
        assert AMBIGUOUS_EXPECTED_KEYS.isdisjoint(expected)
        domain_calls = as_list(expected["domain_calls"], "domain_calls")
        model_tools = as_list(expected["model_tools"], "model_tools")
        unnecessary = as_list(
            expected["unnecessary_model_tools"],
            "unnecessary_model_tools",
        )
        assert isinstance(domain_calls, list)
        assert isinstance(model_tools, list)
        assert isinstance(unnecessary, list)
        outcomes = as_list(expected["allowed_outcomes"], "allowed_outcomes")
        assert outcomes
        evidence_ids = as_object(expected["evidence_ids"], "evidence_ids")
        assert evidence_ids == EVIDENCE_REQUIREMENTS
        when_plan = as_object(
            evidence_ids["when_plan_returned"],
            "when_plan_returned",
        )
        assert when_plan["immutable_revision"] is True
        assert when_plan["catalog_version"] == CATALOG_VERSION
        assert evidence_ids["owner_scoped"] is True
        assert evidence_ids["hidden_reasoning"] == "forbidden"
        assert evidence_ids["fabricate_hashes"] is False
        assert evidence_ids["imply_snapshots_created"] is False
        assert expected["evidence_class"] in EVIDENCE_CLASS_LABELS
        path_classes = as_list(expected["path_classes"], "path_classes")
        assert path_classes
        constraints = as_object(expected["constraint_results"], "constraint_results")
        assert constraints["hidden_reasoning"] == "forbidden"
        assert expected["notice"] == NOTICE
        fixture = as_object(row["fixture_behavior"], "fixture_behavior")
        assert as_str(fixture["kind"], "kind")
        messages = as_list(row["messages"], "messages")
        assert messages
        for message in messages:
            item = as_object(message, "message")
            assert item["role"] == "user"
            assert as_str(item["content"], "content")


def test_recipe_ids_are_supported_except_intentional_unsupported_cases() -> None:
    found: set[str] = set()
    for row in scenarios(load_corpus()):
        scenario_id = as_str(row["id"], "id")
        inputs = as_object(row["inputs"], "inputs")
        expected = as_object(row["expected"], "expected")
        ids = recipe_ids_from(inputs) | recipe_ids_from(expected)
        found |= ids
        for recipe_id in ids:
            if recipe_id in UNSUPPORTED_RECIPE_IDS:
                assert scenario_id == "X02"
                continue
            assert recipe_id in SUPPORTED_RECIPE_IDS
    assert set(SUPPORTED_RECIPE_IDS) <= found
    assert "salmon_tacos" in found


def test_accepted_plans_use_integer_cents_full_ingredients_and_explicit_pantry() -> (
    None
):
    for row in scenarios(load_corpus()):
        expected = as_object(row["expected"], "expected")
        inputs = as_object(row["inputs"], "inputs")
        meals = as_list(inputs.get("meals", []), "meals")
        accepted = expected.get("accepted")
        total = expected.get("total_cents")
        if accepted is not True or total is None:
            continue
        assert type(total) is int
        assert meals
        lines = as_list(expected["lines"], "lines")
        assert lines
        pantry_ids = {
            as_str(
                as_object(line, "line")["ingredient_id"],
                "ingredient_id",
            )
            for line in lines
            if as_bool(as_object(line, "line")["from_pantry"], "from_pantry")
        }
        declared = {
            as_str(item, "pantry")
            for item in as_list(
                inputs.get("pantry_ingredients", []), "pantry_ingredients"
            )
        }
        assert pantry_ids <= declared
        costs = [
            as_int(as_object(line, "line")["cost_cents"], "cost_cents")
            for line in lines
        ]
        assert sum(costs) == total
        for line in lines:
            item = as_object(line, "line")
            assert type(item["quantity"]) is int
            assert type(item["packages"]) is int
            assert type(item["cost_cents"]) is int
            if as_bool(item["from_pantry"], "from_pantry"):
                assert item["packages"] == 0
                assert item["cost_cents"] == 0
        constraints = as_object(expected["constraint_results"], "constraint_results")
        assert constraints["servings_reduced"] is False
        assert constraints["ingredients_omitted"] is False


def test_corpus_file_names_no_instacart() -> None:
    assert "Instacart" not in CORPUS_PATH.read_text(encoding="utf-8")


def test_corpus_does_not_claim_a_fake_success_score() -> None:
    corpus = load_corpus()
    for item in walk(corpus):
        if not isinstance(item, dict):
            continue
        keys = {str(key).lower() for key in item}
        assert keys.isdisjoint(FORBIDDEN_SCORE_KEYS)


def test_secrets_and_provider_urls_stay_out_of_messages_inputs_and_exports() -> None:
    for row in scenarios(load_corpus()):
        scenario_id = as_str(row["id"], "id")
        inspected = {
            "messages": row["messages"],
            "inputs": row["inputs"],
            "expected": row["expected"],
            "prompt": row["prompt"],
        }
        blob = "\n".join(text_blobs(inspected)).lower()
        for token in FORBIDDEN_LEAK_TOKENS:
            if token == SECRET_MARKER.lower():
                assert token not in blob
                continue
            if scenario_id == "A04" and token in PROVIDER_URL_TOKENS:
                continue
            assert token not in blob
        fixture = as_object(row["fixture_behavior"], "fixture_behavior")
        fixture_blob = "\n".join(text_blobs(fixture))
        if scenario_id == "A03":
            provider_fixture = as_object(
                fixture["provider_fixture"], "provider_fixture"
            )
            assert provider_fixture["secret_marker"] == SECRET_MARKER
            assert SECRET_MARKER not in "\n".join(text_blobs(inspected))
            continue
        assert SECRET_MARKER not in fixture_blob


def test_path_classes_and_result_labels_are_covered_separately() -> None:
    rows = scenarios(load_corpus())
    used_labels = {
        as_object(row["expected"], "expected")["evidence_class"] for row in rows
    }
    used_paths: set[str] = set()
    for row in rows:
        expected = as_object(row["expected"], "expected")
        for item in as_list(expected["path_classes"], "path_classes"):
            used_paths.add(as_str(item, "path_class"))
    assert "deterministic_fake_provider" in used_labels
    assert "local_postgresql" in used_labels
    assert "plaid_sandbox" in used_labels
    assert "live_instacart_development" in used_labels
    assert "real_bedrock" in used_labels
    assert set(PATH_CLASSES) <= used_paths
    p05 = next(row for row in rows if row["id"] == "P05")
    expected = as_object(p05["expected"], "P05 expected")
    forbidden = as_list(expected["must_not_substitute"], "must_not_substitute")
    assert "deployed_aws" in forbidden
    assert expected["evidence_class"] != "deployed_aws"


def test_known_totals_and_shared_packages_are_inspectable() -> None:
    by_id = {as_str(row["id"], "id"): row for row in scenarios(load_corpus())}
    for scenario_id, total in MEAL_TOTALS.items():
        expected = as_object(by_id[scenario_id]["expected"], scenario_id)
        assert expected["total_cents"] == total
    m01 = as_object(by_id["M01"]["expected"], "M01")
    assert m01["line_count"] == 7
    m02 = as_object(by_id["M02"]["expected"], "M02")
    shared = as_object(m02["shared"], "shared")
    assert shared == {
        "ingredient_id": "chicken_breast",
        "quantity": 200,
        "packages": 1,
    }
    m03 = as_object(by_id["M03"]["expected"], "M03")
    assert m03["line_count"] == 13
    assert len(as_list(m03["lines"], "M03 lines")) == 13
    m05 = as_object(by_id["M05"]["expected"], "M05")
    potato = next(
        as_object(line, "line")
        for line in as_list(m05["lines"], "M05 lines")
        if as_object(line, "line")["ingredient_id"] == "potato"
    )
    assert potato["quantity"] == 2
    assert potato["packages"] == 1
    b01 = as_object(by_id["B01"]["expected"], "B01")
    assert b01["available_cents"] == 10000
    assert b01["pending_cents"] == 4000
    b02 = as_object(by_id["B02"]["expected"], "B02")
    assert b02["available_cents"] == 1250
    b03 = as_object(by_id["B03"]["expected"], "B03")
    assert b03["available_cents"] == 0
    assert b03["accepted"] is False
    f01 = as_object(by_id["F01"]["expected"], "F01")
    pantry_lines = [
        as_object(line, "line")
        for line in as_list(f01["lines"], "F01 lines")
        if as_bool(as_object(line, "line")["from_pantry"], "from_pantry")
    ]
    assert [line["ingredient_id"] for line in pantry_lines] == ["black_beans"]
    x01 = as_object(by_id["X01"]["expected"], "X01")
    assert x01["total_cents"] is None
    assert x01["accepted"] is False


def test_budget_boundary_and_stale_variants_are_explicit() -> None:
    by_id = {as_str(row["id"], "id"): row for row in scenarios(load_corpus())}
    b04 = by_id["B04"]
    variants = [as_object(item, "variant") for item in as_list(b04["variants"], "B04")]
    assert variants[0]["now"] == "2026-10-01T03:30:00Z"
    assert variants[0]["period_match"] is True
    assert variants[1]["now"] == "2026-10-01T04:00:00Z"
    assert variants[1]["period_match"] is False
    b05 = by_id["B05"]
    stale = [as_object(item, "variant") for item in as_list(b05["variants"], "B05")]
    assert stale[0]["plan_cap_cents"] is None
    assert stale[1]["plan_cap_cents"] == 2000
    assert stale[1]["available_cents"] == 2000
    assert stale[2]["elapsed_hours_utc"] == 25
    assert stale[2]["now"] == "2026-11-02T05:00:00Z"


def test_failure_classes_keep_one_inspectable_example() -> None:
    by_id = {as_str(row["id"], "id"): row for row in scenarios(load_corpus())}
    x02 = as_object(by_id["X02"]["expected"], "X02")
    x03 = as_object(by_id["X03"]["expected"], "X03")
    f03 = as_object(by_id["F03"]["expected"], "F03")
    p03 = as_object(by_id["P03"]["expected"], "P03")
    p04 = as_object(by_id["P04"]["expected"], "P04")
    p05 = as_object(by_id["P05"]["expected"], "P05")
    a01 = as_object(by_id["A01"]["expected"], "A01")
    a04 = as_object(by_id["A04"]["expected"], "A04")
    f03_constraints = as_object(f03["constraint_results"], "F03 constraints")
    assert x02["unsupported_recipe_id"] == "salmon_tacos"
    assert x03["unknown_restriction_ids"] == ["mystery_spice", "nightshades"]
    assert f03_constraints["exclusion_before_pantry"] is True
    assert p03["fake_answer_forbidden"] is True
    assert p04["max_model_turns"] == 8
    assert p04["max_planner_revisions"] == 3
    assert p05["duplicate_handoff"] is False
    assert a01["false_affordable_claim"] is False
    assert a04["purchase_attempt"] is False
    x04_row = by_id["X04"]
    p01_row = by_id["P01"]
    p02_row = by_id["P02"]
    p05_row = by_id["P05"]
    assert as_bool(x04_row["requires_model"], "X04 requires_model") is True
    assert as_bool(p01_row["requires_model"], "P01 requires_model") is False
    assert as_bool(p02_row["requires_model"], "P02 requires_model") is False
    assert as_bool(p05_row["requires_model"], "P05 requires_model") is False
    x04_expected = as_object(x04_row["expected"], "X04 expected")
    p01_expected = as_object(p01_row["expected"], "P01 expected")
    p02_expected = as_object(p02_row["expected"], "P02 expected")
    p05_expected = as_object(p05_row["expected"], "P05 expected")
    assert call_names(as_list(x04_expected["domain_calls"], "X04 domain"), "X04") == [
        "calculate_budget"
    ]
    assert call_names(as_list(x04_expected["model_tools"], "X04 model"), "X04") == [
        MODEL_TOOL_NAME
    ]
    assert as_list(p01_expected["model_tools"], "P01 model") == []
    assert call_names(as_list(p01_expected["domain_calls"], "P01 domain"), "P01") == [
        "sync_item",
        "calculate_budget",
    ]
    p01_constraints = as_object(p01_expected["constraint_results"], "P01 constraints")
    assert p01_constraints["fresh_claim_forbidden"] is True
    assert p01_constraints["stale_spending"] == "refresh_failed"
    assert p01_expected["evidence_class"] == "plaid_sandbox"
    assert as_list(p02_expected["model_tools"], "P02 model") == []
    assert call_names(as_list(p02_expected["domain_calls"], "P02 domain"), "P02") == [
        "plan_groceries",
        "prepare_handoff",
        "dispatch_handoff",
    ]
    p02_constraints = as_object(p02_expected["constraint_results"], "P02 constraints")
    assert p02_constraints["automatic_duplicate"] is False
    assert p02_constraints["handoff_uncertain"] is True
    assert p02_expected["evidence_class"] == "live_instacart_development"
    assert as_list(p05_expected["model_tools"], "P05 model") == []
    assert call_names(as_list(p05_expected["domain_calls"], "P05 domain"), "P05") == [
        "create_job",
        "process_one",
        "prepare_handoff",
        "dispatch_handoff",
    ]
    for row in by_id.values():
        expected_row = as_object(row["expected"], "expected")
        for item in as_list(expected_row["domain_calls"], "domain_calls"):
            call = as_object(item, "domain_call")
            if as_str(call["name"], "name") != "create_job":
                continue
            expectation = as_object(call["expectation"], "create_job expectation")
            assert as_str(expectation["kind"], "kind") in JOB_KINDS
    create_job = as_object(
        as_list(p05_expected["domain_calls"], "P05 domain")[0],
        "P05 create_job",
    )
    create_expectation = as_object(create_job["expectation"], "P05 create expectation")
    assert create_expectation["kind"] == "agent"
    assert as_list(a04["unnecessary_model_tools"], "A04 unnecessary") == [
        "create_shopping_handoff"
    ]


def test_evidence_ids_stay_conditional_and_do_not_invent_hashes() -> None:
    corpus = load_corpus()
    source = CORPUS_PATH.read_text(encoding="utf-8")
    for token in INVENTED_EVIDENCE_ID_TOKENS:
        assert token not in source
    for item in walk(corpus):
        if type(item) is not str:
            continue
        assert len(item) != 64 or any(char not in "0123456789abcdef" for char in item)
    for row in scenarios(corpus):
        expected = as_object(row["expected"], "expected")
        assert expected["evidence_ids"] == EVIDENCE_REQUIREMENTS
        variants = row.get("variants")
        if variants is None:
            continue
        for item in as_list(variants, "variants"):
            variant = as_object(item, "variant")
            if "evidence_ids" not in variant:
                continue
            assert variant["evidence_ids"] == EVIDENCE_REQUIREMENTS


def test_corpus_is_thirty_cases_not_a_ninety_run_harness() -> None:
    corpus = load_corpus()
    rows = scenarios(corpus)
    assert len(rows) == 30
    assert as_int(corpus["repeats"], "repeats") == REPEATS
    source = CORPUS_PATH.read_text(encoding="utf-8")
    assert "success_score" not in source
    assert "90 cases" not in source.lower()
    assert "90 runs" not in source.lower()
    assert "live score" not in source.lower()
    assert "model score" not in source.lower()
    assert corpus["metrics_status"] == "unassessed"


def test_supported_recipe_list_matches_the_catalog() -> None:
    corpus = load_corpus()
    listed = as_list(corpus["supported_recipe_ids"], "supported_recipe_ids")
    assert [as_str(item, "recipe") for item in listed] == list(SUPPORTED_RECIPE_IDS)


def test_messages_are_sequences_of_role_content_objects() -> None:
    for row in scenarios(load_corpus()):
        messages = as_list(row["messages"], "messages")
        assert isinstance(messages, Sequence)
        prompt = as_str(row["prompt"], "prompt")
        first = as_object(messages[0], "first message")
        assert as_str(first["content"], "content")
        assert prompt
        inputs = as_object(row["inputs"], "inputs")
        period = as_str(inputs["budget_period"], "budget_period")
        assert period.endswith("-01")
        assert "now" in inputs or "variants" in row
