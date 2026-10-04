import json
from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import pytest

from app import evaluation_batch as batch
from app import evaluation_dispatch as dispatch
from app import evaluation_matrix as matrix
from app import evaluation_runner as legacy
from app.domain.catalog import CATALOG_VERSION
from app.evaluation_manifest import build_manifest
from app.evaluation_matrix import EvaluationSlot

REVISION = "a" * 40
CONFIG: dict[str, object] = {"max_tokens": 128, "temperature": 0}


def _corpus() -> dict[str, object]:
    cases: list[dict[str, object]] = []
    for case_id, group in matrix._GROUPS.items():
        cases.append(
            {
                "id": case_id,
                "group": group,
                "requires_model": case_id in matrix.MODEL_CASE_IDS or case_id == "P04",
                "prompt": "Plan a meal.",
                "messages": [{"role": "user", "content": "Plan a meal."}],
                "inputs": {"public_fact": "original"},
                "expected": {
                    "domain_calls": [],
                    "model_tools": [],
                    "allowed_outcomes": ["planned"],
                    "unnecessary_model_tools": [],
                },
                "fixture_behavior": {"kind": "fixture", "provider": "fake"},
            }
        )
    return {
        "version": "grocery-eval-v1",
        "catalog_version": CATALOG_VERSION,
        "repeats": 3,
        "metrics_status": "unassessed",
        "scenarios": cases,
    }


def _runtime() -> dispatch.EvaluationRuntime:
    return cast(
        dispatch.EvaluationRuntime,
        SimpleNamespace(
            model_id="fake-model",
            evidence_class="deterministic_fake_provider",
            provider_factory=Mock(return_value=object()),
            database_url=None,
            endpoint=None,
        ),
    )


def _result(slot: EvaluationSlot, manifest: dict[str, object]) -> dict[str, object]:
    prompt = (
        "baseline_system_prompt_hash"
        if slot.driver == "no_tool"
        else "system_prompt_hash"
    )
    return {
        "case_id": slot.case_id,
        "repeat": slot.repeat,
        "condition": slot.condition,
        "driver": slot.driver,
        "status": "completed",
        "elapsed_seconds": 0.0,
        "observation": {
            "status": "completed",
            "model_id": manifest["model_id"],
            "catalog_version": manifest["catalog_version"],
            "catalog_hash": manifest["catalog_hash"],
            "system_prompt_hash": manifest[prompt],
            "evidence_class": "deterministic_fake_provider",
            "turns": [{"status": "completed", "result": {"answer": "original"}}],
        },
        "assessments": {},
        "report": None,
    }


def _run(
    corpus: dict[str, object],
    runtime: dispatch.EvaluationRuntime,
    *,
    model_config: dict[str, object] | None = None,
    on_slot: Callable[[dict[str, object]], None] | None = None,
) -> dict[str, object]:
    return batch.run_evaluation_batch(
        corpus,
        runtime,
        region="us-east-1",
        model_config=CONFIG if model_config is None else model_config,
        revision=REVISION,
        on_slot=on_slot,
    )


@pytest.fixture
def harness(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, object], dispatch.EvaluationRuntime, Mock]:
    corpus, runtime = _corpus(), _runtime()
    manifest = build_manifest(
        corpus, model_id=runtime.model_id, region="us-east-1", model_config=CONFIG
    )

    def execute(
        slot: EvaluationSlot, current: dispatch.EvaluationRuntime
    ) -> dict[str, object]:
        assert current is runtime
        assert cast(dict[str, object], slot.case["inputs"])["public_fact"] == "original"
        return _result(slot, manifest)

    runner = Mock(side_effect=execute)
    monkeypatch.setattr(batch, "run_slot", runner)
    return corpus, runtime, runner


def _slots(result: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], result["slots"]) + cast(
        list[dict[str, object]], result["baseline_slots"]
    )


def test_complete_matrix_and_pinned_conditions(
    harness: tuple[dict[str, object], dispatch.EvaluationRuntime, Mock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus, runtime, runner = harness
    journal: list[dict[str, object]] = []
    builder = Mock(wraps=batch.build_manifest)
    monkeypatch.setattr(batch, "build_manifest", builder)
    result = _run(corpus, runtime, on_slot=journal.append)
    slots = _slots(result)
    assert result["mode"] == "complete_evaluation"
    assert result["revision"] == REVISION
    assert result["primary_slot_count"] == result["slot_count"] == 90
    assert result["total_slot_count"] == len(slots) == len(journal) == 138
    assert len(cast(list[object], result["baseline_slots"])) == 48
    assert len({(s["case_id"], s["repeat"], s["condition"]) for s in slots}) == 138
    for case_id in matrix._GROUPS:
        assert [s["repeat"] for s in slots[:90] if s["case_id"] == case_id] == [1, 2, 3]
    assert [s["condition"] for s in slots[90:123]] == ["no_tool"] * 33
    assert [s["condition"] for s in slots[123:]] == ["deterministic"] * 15
    assert journal == slots
    assert runner.call_count == 138
    builder.assert_called_once()
    manifest = cast(dict[str, object], result["manifest"])
    for slot in slots:
        if slot["driver"] not in ("model", "no_tool"):
            continue
        observed = cast(dict[str, object], slot["observation"])
        assert observed["model_id"] == manifest["model_id"] == runtime.model_id
        assert observed["catalog_version"] == manifest["catalog_version"]
        assert observed["catalog_hash"] == manifest["catalog_hash"]
        key = (
            "system_prompt_hash"
            if slot["driver"] == "model"
            else "baseline_system_prompt_hash"
        )
        assert observed["system_prompt_hash"] == manifest[key]
    started = datetime.fromisoformat(cast(str, result["started_at"]))
    finished = datetime.fromisoformat(cast(str, result["finished_at"]))
    assert started.tzinfo == finished.tzinfo == UTC
    assert finished >= started
    private_keys = {"provider", "provider_factory", "database_url", "profile"}
    assert not private_keys & result.keys()
    assert not private_keys & manifest.keys()


def test_callbacks_cannot_mutate_results_or_frozen_sources(
    harness: tuple[dict[str, object], dispatch.EvaluationRuntime, Mock],
) -> None:
    corpus, runtime, runner = harness
    original = deepcopy(corpus)
    config = deepcopy(CONFIG)
    expected_manifest = build_manifest(
        original, model_id=runtime.model_id, region="us-east-1", model_config=config
    )

    def mutate(slot: dict[str, object]) -> None:
        cases = cast(list[dict[str, object]], corpus.get("scenarios", []))
        if cases:
            cast(dict[str, object], cases[0]["inputs"])["public_fact"] = "changed"
        corpus["scenarios"] = []
        corpus["version"] = "changed"
        config["max_tokens"] = 4096
        observation = cast(dict[str, object], slot["observation"])
        observation["model_id"] = "changed"
        cast(list[object], observation["turns"]).clear()
        cast(dict[str, object], slot["assessments"])["changed"] = True
        slot.clear()

    result = _run(corpus, runtime, model_config=config, on_slot=mutate)
    assert runner.call_count == 138
    assert result["version"] == original["version"]
    assert result["manifest"] == expected_manifest
    for slot in _slots(result):
        observation = cast(dict[str, object], slot["observation"])
        assert observation["model_id"] == "fake-model"
        assert len(cast(list[object], observation["turns"])) == 1
        assert slot["assessments"] == {}


@pytest.mark.parametrize("driver", ["model", "no_tool"])
@pytest.mark.parametrize(
    "field",
    [
        "model_id",
        "evidence_class",
        "catalog_version",
        "catalog_hash",
        "system_prompt_hash",
    ],
)
def test_contract_mismatch_fails_without_replacing_captured_fields(
    harness: tuple[dict[str, object], dispatch.EvaluationRuntime, Mock],
    monkeypatch: pytest.MonkeyPatch,
    driver: str,
    field: str,
) -> None:
    corpus, runtime, runner = harness
    execute = runner.side_effect

    def mismatch(
        slot: EvaluationSlot, current: dispatch.EvaluationRuntime
    ) -> dict[str, object]:
        result = cast(dict[str, object], execute(slot, current))
        if slot.driver == driver:
            cast(dict[str, object], result["observation"])[field] = "wrong-contract"
        return result

    monkeypatch.setattr(batch, "run_slot", mismatch)
    result = _run(corpus, runtime)
    assert result["metrics_status"] == "partial"
    for slot in _slots(result):
        if slot["driver"] == driver:
            assert slot["status"] == "failed"
            assert slot["reason_code"] == "evidence_contract_mismatch"
            observation = cast(dict[str, object], slot["observation"])
            assert observation[field] == "wrong-contract"
            assert observation["status"] == "completed"
            assert batch.classify_slot(slot).quality_status == "failed"
        else:
            assert slot["status"] == "completed"


def test_tool_observation_can_omit_catalog_hash(
    harness: tuple[dict[str, object], dispatch.EvaluationRuntime, Mock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus, runtime, runner = harness
    execute = runner.side_effect

    def omit_hash(
        slot: EvaluationSlot, current: dispatch.EvaluationRuntime
    ) -> dict[str, object]:
        result = cast(dict[str, object], execute(slot, current))
        if slot.driver == "model":
            cast(dict[str, object], result["observation"]).pop("catalog_hash")
        return result

    monkeypatch.setattr(batch, "run_slot", omit_hash)
    assert all(s["status"] == "completed" for s in _slots(_run(corpus, runtime)))


@pytest.mark.parametrize(
    "invalid",
    ["revision", "corpus", "duplicate", "config", "model", "evidence", "region"],
)
def test_invalid_inputs_fail_before_execution_or_callbacks(
    harness: tuple[dict[str, object], dispatch.EvaluationRuntime, Mock],
    invalid: str,
) -> None:
    corpus, runtime, runner = harness
    config, revision, region = deepcopy(CONFIG), REVISION, "us-east-1"
    if invalid == "revision":
        revision = "A" * 40
    elif invalid == "corpus":
        corpus["repeats"] = True
    elif invalid == "duplicate":
        cases = cast(list[dict[str, object]], corpus["scenarios"])
        cases[-1] = deepcopy(cases[0])
    elif invalid == "config":
        config["unapproved_field"] = "not-public"
    elif invalid == "model":
        cast(SimpleNamespace, runtime).model_id = "invalid model"
    elif invalid == "evidence":
        cast(SimpleNamespace, runtime).evidence_class = "unknown"
    else:
        region = "unapproved-region"
    callback = Mock()
    with pytest.raises(ValueError):
        batch.run_evaluation_batch(
            corpus,
            runtime,
            model_config=config,
            region=region,
            revision=revision,
            on_slot=callback,
        )
    runner.assert_not_called()
    cast(Mock, runtime.provider_factory).assert_not_called()
    callback.assert_not_called()


@pytest.mark.parametrize("corruption", ["missing", "duplicate", "order"])
def test_invalid_prepared_matrix_cannot_silently_run(
    harness: tuple[dict[str, object], dispatch.EvaluationRuntime, Mock],
    monkeypatch: pytest.MonkeyPatch,
    corruption: str,
) -> None:
    corpus, runtime, runner = harness
    matrix = batch.prepare_matrix(corpus)
    if corruption == "missing":
        matrix.pop()
    elif corruption == "duplicate":
        matrix[-1] = matrix[-2]
    else:
        matrix[0], matrix[90] = matrix[90], matrix[0]
    monkeypatch.setattr(batch, "prepare_matrix", Mock(return_value=matrix))
    callback = Mock()
    with pytest.raises(ValueError, match="invalid evaluation matrix"):
        _run(corpus, runtime, on_slot=callback)
    runner.assert_not_called()
    callback.assert_not_called()


def _source_corpus(actual: bool) -> dict[str, object]:
    if not actual:
        return _corpus()
    path = Path(__file__).parent / "evaluation" / "scenarios.json"
    return cast(dict[str, object], json.loads(path.read_text()))


@pytest.mark.parametrize("actual", [False, True], ids=["synthetic", "actual"])
@pytest.mark.parametrize(
    "corruption",
    [
        "missing_case",
        "substituted_case",
        "repeat_four",
        "primary_condition",
        "primary_order",
        "no_tool_order",
        "reference_order",
    ],
)
def test_unique_wrong_matrix_fails_before_execution_or_callbacks(
    monkeypatch: pytest.MonkeyPatch,
    actual: bool,
    corruption: str,
) -> None:
    corpus, runtime = _source_corpus(actual), _runtime()
    slots = batch.prepare_matrix(corpus)
    if corruption == "missing_case":
        slots[:3] = [replace(slots[3], repeat=repeat) for repeat in range(4, 7)]
    elif corruption == "substituted_case":
        slots[0] = replace(slots[0], case_id="P04")
    elif corruption == "repeat_four":
        slots[2] = replace(slots[2], repeat=4)
    elif corruption == "primary_condition":
        slots[0] = replace(slots[0], condition="controlled_fixture")
    else:
        index = {"primary_order": 0, "no_tool_order": 90, "reference_order": 123}[
            corruption
        ]
        slots[index], slots[index + 3] = slots[index + 3], slots[index]
    assert len(slots) == 138
    assert len({(slot.case_id, slot.repeat, slot.condition) for slot in slots}) == 138
    monkeypatch.setattr(batch, "prepare_matrix", Mock(return_value=slots))
    runner, callback = Mock(), Mock()
    monkeypatch.setattr(batch, "run_slot", runner)
    with pytest.raises(ValueError) as raised:
        _run(corpus, runtime, on_slot=callback)
    assert str(raised.value) == "invalid evaluation matrix"
    runner.assert_not_called()
    cast(Mock, runtime.provider_factory).assert_not_called()
    callback.assert_not_called()


@pytest.mark.parametrize("actual", [False, True], ids=["synthetic", "actual"])
@pytest.mark.parametrize("reverse", [False, True])
def test_valid_matrix_uses_corpus_order_and_fixed_cohorts(
    monkeypatch: pytest.MonkeyPatch, actual: bool, reverse: bool
) -> None:
    corpus, runtime = _source_corpus(actual), _runtime()
    cases = cast(list[dict[str, object]], corpus["scenarios"])
    if reverse:
        cases.reverse()
    manifest = build_manifest(
        corpus, model_id=runtime.model_id, region="us-east-1", model_config=CONFIG
    )

    def execute(
        slot: EvaluationSlot, current: dispatch.EvaluationRuntime
    ) -> dict[str, object]:
        assert current is runtime
        return _result(slot, manifest)

    runner = Mock(side_effect=execute)
    monkeypatch.setattr(batch, "run_slot", runner)
    slots = _slots(_run(corpus, runtime))
    for section, cohort in (
        (slots[:90], {cast(str, case["id"]) for case in cases}),
        (slots[90:123], matrix.MODEL_CASE_IDS),
        (slots[123:], matrix.REFERENCE_CASE_IDS),
    ):
        assert [(slot["case_id"], slot["repeat"]) for slot in section] == [
            (case["id"], repeat)
            for case in cases
            if case["id"] in cohort
            for repeat in (1, 2, 3)
        ]
    assert runner.call_count == 138
    assert {s["condition"] for s in slots[90:123]} == {"no_tool"}
    assert {s["condition"] for s in slots[123:]} == {"deterministic"}
    provider_slots = [s for s in slots[:90] if s["case_id"] == "P04"]
    assert {s["condition"] for s in provider_slots} == {"controlled_fixture"}


@pytest.mark.parametrize("interrupted", [False, True])
def test_callback_failure_stops_after_actual_slot(
    harness: tuple[dict[str, object], dispatch.EvaluationRuntime, Mock],
    interrupted: bool,
) -> None:
    corpus, runtime, runner = harness
    journal: list[dict[str, object]] = []

    def callback(slot: dict[str, object]) -> None:
        journal.append(slot)
        if len(journal) == 3:
            if interrupted:
                raise KeyboardInterrupt
            raise ValueError("private exception detail")

    exception = KeyboardInterrupt if interrupted else RuntimeError
    with pytest.raises(exception) as raised:
        _run(corpus, runtime, on_slot=callback)
    assert runner.call_count == len(journal) == 3
    if not interrupted:
        assert str(raised.value) == "evaluation slot callback failed"
        assert raised.value.__suppress_context__ is True


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        (["passed"] * 138, "assessed"),
        (["failed"] * 138, "assessed"),
        (["passed"] * 137 + ["unassessed"], "partial"),
        (["unassessed"] * 138, "unassessed"),
    ],
)
def test_metrics_status_reports_assessment_coverage(
    harness: tuple[dict[str, object], dispatch.EvaluationRuntime, Mock],
    monkeypatch: pytest.MonkeyPatch,
    statuses: list[str],
    expected: str,
) -> None:
    corpus, runtime, _ = harness
    classifier = Mock(
        side_effect=[SimpleNamespace(quality_status=status) for status in statuses]
    )
    monkeypatch.setattr(batch, "classify_slot", classifier)
    result = _run(corpus, runtime)
    assert result["metrics_status"] == expected
    assert classifier.call_count == 138
    assert "pass_percentage" not in result


def test_missing_assessments_cannot_inherit_corpus_success(
    harness: tuple[dict[str, object], dispatch.EvaluationRuntime, Mock],
) -> None:
    corpus, runtime, _ = harness
    corpus["metrics_status"] = "assessed"
    assert _run(corpus, runtime)["metrics_status"] == "unassessed"


def test_dispatch_propagates_keyboard_interrupt() -> None:
    runtime = _runtime()
    cast(Mock, runtime.provider_factory).side_effect = KeyboardInterrupt
    slot = next(
        slot for slot in batch.prepare_matrix(_corpus()) if slot.driver == "model"
    )
    with pytest.raises(KeyboardInterrupt):
        dispatch.run_slot(slot, runtime)


def test_dispatch_isolates_model_failure_and_runs_later_slots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus, runtime = _corpus(), _runtime()
    manifest = build_manifest(
        corpus, model_id=runtime.model_id, region="us-east-1", model_config=CONFIG
    )
    observed_ids: list[str] = []

    def observe(
        case: dict[str, object],
        provider: object,
        *,
        evidence_class: str,
        model_id: str,
    ) -> dict[str, object]:
        assert "expected" not in case
        assert model_id == manifest["model_id"]
        assert evidence_class == "deterministic_fake_provider"
        case_id = cast(str, case["id"])
        observed_ids.append(case_id)
        if len(observed_ids) == 1:
            raise RuntimeError("private provider exception detail")
        slot = EvaluationSlot(case_id, 1, "tool_enabled", "model", case)
        result = _result(slot, manifest)
        return cast(dict[str, object], result["observation"])

    def no_tool(
        case: dict[str, object],
        provider: object,
        *,
        evidence_class: str,
        model_id: str,
    ) -> dict[str, object]:
        observation = observe(
            case, provider, evidence_class=evidence_class, model_id=model_id
        )
        observation["system_prompt_hash"] = manifest["baseline_system_prompt_hash"]
        return observation

    def fixture(case: dict[str, object]) -> dict[str, object]:
        return {
            "case_id": case["id"],
            "status": "passed",
            "checks": {"guard": True},
            "evidence_class": "deterministic_fake_provider",
            "evidence_paths": ["deterministic_fake_provider"],
        }

    monkeypatch.setattr(dispatch, "observe_model_case", observe)
    monkeypatch.setattr(dispatch, "observe_no_tool_case", no_tool)
    monkeypatch.setattr(
        dispatch, "observe_reference_case", Mock(return_value={"status": "failed"})
    )
    monkeypatch.setattr(
        dispatch, "_FIXTURES", dict.fromkeys(dispatch._FIXTURES, fixture)
    )
    monkeypatch.setattr(
        dispatch, "_SCORERS", {"plan": Mock(return_value={"status": "unassessed"})}
    )
    monkeypatch.setattr(
        dispatch, "score_plan", Mock(return_value={"status": "unassessed"})
    )
    journal: list[dict[str, object]] = []
    result = _run(corpus, runtime, on_slot=journal.append)
    slots = _slots(result)
    model_slots = [slot for slot in slots if slot["driver"] == "model"]
    assert len(slots) == len(journal) == 138
    assert model_slots[0]["status"] == "failed"
    assert model_slots[1]["status"] == "completed"
    assert len(observed_ids) == 66
    assert "private provider exception detail" not in repr(result)


def test_legacy_fixture_api_retains_42_scored_and_48_unassessed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluator = Mock(return_value={"status": "passed"})
    for name in (
        "evaluate_budget_case",
        "evaluate_meal_case",
        "evaluate_followup_case",
        "evaluate_missing_case",
    ):
        monkeypatch.setattr(legacy, name, evaluator)
    result = legacy.run_evaluation(_corpus())
    slots = cast(list[dict[str, object]], result["slots"])
    assert result["slot_count"] == len(slots) == 90
    assert sum(slot["status"] == "scored" for slot in slots) == 42
    assert sum(slot["status"] == "unassessed" for slot in slots) == 48
    assert result["metrics_status"] == "unassessed"
    assert "baseline_slots" not in result
