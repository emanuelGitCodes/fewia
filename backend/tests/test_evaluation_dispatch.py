import json
from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from app import evaluation_dispatch as dispatch
from app.agent.provider import LLMProvider
from app.evaluation_matrix import EvaluationSlot, prepare_matrix
from app.evaluation_runtime import EvaluationRuntime, fixture_result


def _map(value: object) -> dict[str, object]:
    assert type(value) is dict
    return cast(dict[str, object], value)


@pytest.fixture
def slots() -> list[EvaluationSlot]:
    path = Path(__file__).parent / "evaluation" / "scenarios.json"
    return prepare_matrix(_map(json.loads(path.read_text())))


def _slot(slots: list[EvaluationSlot], case_id: str, driver: str) -> EvaluationSlot:
    return next(s for s in slots if s.case_id == case_id and s.driver == driver)


def _unused_factory() -> LLMProvider:
    raise AssertionError("The provider factory MUST remain unused.")


def _runtime(factory: Callable[[], LLMProvider] = _unused_factory) -> EvaluationRuntime:
    return EvaluationRuntime(factory, "test-model", "deterministic_fake_provider")


def _assert_frame(result: dict[str, object], slot: EvaluationSlot) -> None:
    assert set(result) == {
        "case_id",
        "repeat",
        "condition",
        "driver",
        "status",
        "elapsed_seconds",
        "observation",
        "assessments",
        "report",
    }
    assert result["case_id"] == slot.case_id
    assert result["repeat"] == slot.repeat
    assert result["condition"] == slot.condition
    assert result["driver"] == slot.driver
    assert result["status"] == _map(result["observation"])["status"]
    assert isinstance(result["elapsed_seconds"], float)
    assert cast(float, result["elapsed_seconds"]) > 0


class RecordingProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        self.calls.append(
            deepcopy({"system": system_prompt, "messages": messages, "tools": tools})
        )
        answer = "Which meals and servings would you like?"
        text = (
            answer
            if tools
            else json.dumps(
                {
                    "status": "clarification",
                    "answer": answer,
                    "request": None,
                    "plan": None,
                    "budget": None,
                }
            )
        )
        return {
            "stopReason": "end_turn",
            "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
            "usage": {"inputTokens": 5, "outputTokens": 7},
        }


def test_public_runtime_reexport() -> None:
    assert dispatch.EvaluationRuntime is EvaluationRuntime


def test_every_matrix_slot_uses_its_driver(
    slots: list[EvaluationSlot], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[str, str]] = []
    providers: list[RecordingProvider] = []

    def factory() -> LLMProvider:
        provider = RecordingProvider()
        providers.append(provider)
        return provider

    def fixture(driver: str) -> Callable[[dict[str, object]], dict[str, object]]:
        def evaluate(case: dict[str, object]) -> dict[str, object]:
            seen.append((driver, cast(str, case["id"])))
            return {"checks": {"guard": True}, "evidence_class": "local_postgresql"}

        return evaluate

    def observer(driver: str) -> Callable[..., dict[str, object]]:
        def observe(
            case: dict[str, object],
            provider: LLMProvider | None = None,
            **kwargs: object,
        ) -> dict[str, object]:
            seen.append((driver, cast(str, case["id"])))
            assert "expected" not in case
            if driver != "reference":
                assert provider is providers[-1]
                assert kwargs == {
                    "model_id": "test-model",
                    "evidence_class": "deterministic_fake_provider",
                }
            return {
                "case_id": case["id"],
                "condition": {
                    "model": "tool_enabled",
                    "no_tool": "no_tool",
                    "reference": "deterministic",
                }[driver],
                "status": "completed",
                "turns": [],
                "final_only": driver == "reference",
            }

        return observe

    for driver in (
        "budget",
        "meals",
        "followup",
        "missing",
        "refresh",
        "handoff",
        "protocol",
    ):
        monkeypatch.setitem(dispatch._FIXTURES, driver, fixture(driver))
    monkeypatch.setattr(dispatch, "observe_model_case", observer("model"))
    monkeypatch.setattr(dispatch, "observe_no_tool_case", observer("no_tool"))
    monkeypatch.setattr(dispatch, "observe_reference_case", observer("reference"))

    def duplicate(case: dict[str, object], **kwargs: str) -> dict[str, object]:
        assert kwargs == {"database_url": "local-db", "endpoint": "local-endpoint"}
        return fixture("duplicate")(case)

    monkeypatch.setattr(dispatch, "evaluate_duplicate_case", duplicate)
    runtime = replace(
        _runtime(factory), database_url="local-db", endpoint="local-endpoint"
    )
    before = deepcopy(slots)
    for slot in slots:
        result = dispatch.run_slot(slot, runtime)
        _assert_frame(result, slot)
        assert seen[-1] == (slot.driver, slot.case_id)
        assessments = _map(result["assessments"])
        if slot.driver in ("model", "no_tool"):
            assert set(assessments) == {"tools", "plan", "outcome", "claims"}
        elif slot.driver == "reference":
            assert set(assessments) == {"plan"}
            assert _map(result["observation"])["final_only"] is True
        else:
            assert set(assessments) == {"fixture"}
            assert _map(result["observation"])["model_quality_applicable"] is False
    assert slots == before
    assert len(providers) == sum(s.driver in ("model", "no_tool") for s in slots)
    assert len({id(provider) for provider in providers}) == len(providers)
    assert len(seen) == len(slots)


@pytest.mark.parametrize("driver", ["model", "no_tool"])
def test_real_observers_keep_gold_out_of_provider_inputs(
    slots: list[EvaluationSlot], driver: str
) -> None:
    slot = _slot(slots, "F04", driver)
    before = deepcopy(slot.case)
    providers: list[RecordingProvider] = []

    def factory() -> LLMProvider:
        provider = RecordingProvider()
        providers.append(provider)
        return provider

    original = dispatch.run_slot(slot, _runtime(factory))
    poisoned = deepcopy(slot.case)
    gold: dict[str, object] = {
        "driver": "duplicate",
        "model_tools": [],
        "secret": "GOLD_MARKER",
    }
    poisoned["expected"] = deepcopy(gold)
    changed = dispatch.run_slot(
        replace(slot, case=poisoned, repeat=2), _runtime(factory)
    )
    assert original["status"] == changed["status"] == "completed"
    assert len(providers) == 2
    assert providers[0] is not providers[1]
    assert providers[0].calls == providers[1].calls
    assert providers[0].calls
    assert "GOLD_MARKER" not in repr(providers[1].calls)
    assert slot.case == before
    assert poisoned["expected"] == gold
    _assert_frame(original, slot)
    observation = _map(original["observation"])
    assert _map(original["assessments"]) == {
        "tools": dispatch.score_tools(slot.case, observation),
        "plan": dispatch.score_plan(slot.case, observation),
        "outcome": dispatch.score_outcome(slot.case, observation),
        "claims": dispatch.score_claims(slot.case, observation),
    }


@pytest.mark.parametrize(
    "case_id,driver",
    [
        ("B01", "budget"),
        ("M01", "meals"),
        ("F03", "followup"),
        ("X01", "missing"),
        ("P01", "refresh"),
        ("P02", "handoff"),
        ("P03", "protocol"),
        ("P04", "protocol"),
    ],
)
def test_real_fixture_reports_without_provider(
    slots: list[EvaluationSlot], case_id: str, driver: str
) -> None:
    slot = _slot(slots, case_id, driver)
    before = deepcopy(slot.case)
    expected = dispatch._FIXTURES[driver](deepcopy(slot.case))
    result = dispatch.run_slot(slot, _runtime())
    _assert_frame(result, slot)
    assert result["status"] == "completed"
    assert result["report"] == expected
    normalized = fixture_result(slot, expected)
    assert result["observation"] == normalized["observation"]
    assert result["assessments"] == normalized["assessments"]
    assert _map(result["observation"])["model_quality_applicable"] is False
    assert slot.case == before


def test_real_reference_preserves_final_only_plan(slots: list[EvaluationSlot]) -> None:
    slot = _slot(slots, "F01", "reference")
    before = deepcopy(slot.case)
    result = dispatch.run_slot(slot, _runtime())
    observation = _map(result["observation"])
    assert result["status"] == "completed"
    assert observation["final_only"] is True
    assert len(cast(list[object], observation["turns"])) == 1
    assert result["assessments"] == {
        "plan": dispatch.score_plan(slot.case, observation),
    }
    assert result["report"] is None
    assert slot.case == before


def test_reference_outside_cohort_is_unassessed(slots: list[EvaluationSlot]) -> None:
    slot = replace(
        _slot(slots, "B01", "budget"), driver="reference", condition="deterministic"
    )
    result = dispatch.run_slot(slot, _runtime())
    assert result["status"] == _map(result["observation"])["status"] == "unassessed"
    assert set(_map(result["assessments"])) == {"plan"}


@pytest.mark.parametrize(
    "database_url,endpoint",
    [
        (None, None),
        ("local-db", None),
        (None, "local-endpoint"),
        ("", "local-endpoint"),
        ("local-db", ""),
    ],
)
def test_duplicate_requires_both_local_services(
    slots: list[EvaluationSlot],
    monkeypatch: pytest.MonkeyPatch,
    database_url: str | None,
    endpoint: str | None,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("The duplicate driver MUST remain unused.")

    monkeypatch.setattr(dispatch, "evaluate_duplicate_case", forbidden)
    slot = _slot(slots, "P05", "duplicate")
    runtime = replace(_runtime(), database_url=database_url, endpoint=endpoint)
    result = dispatch.run_slot(slot, runtime)
    assert result["status"] == "unassessed"
    observation = _map(result["observation"])
    assert observation["reason_code"] == "missing_local_services"
    assert observation["evidence_class"] == "unknown"
    assert observation["evidence_paths"] == observation["turns"] == []
    assert _map(_map(result["assessments"])["fixture"])["checks"] == {}


@pytest.mark.parametrize("status", ["completed", "failed", "partial", "unassessed"])
@pytest.mark.parametrize("driver", ["model", "no_tool"])
def test_observer_status_and_exact_scores_are_distinct(
    slots: list[EvaluationSlot],
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    driver: str,
) -> None:
    observation: dict[str, object] = {
        "status": status,
        "turns": [],
        "extra": "retained",
    }

    def observe(*args: object, **kwargs: object) -> dict[str, object]:
        return observation

    monkeypatch.setattr(dispatch, f"observe_{driver}_case", observe)
    scores: dict[str, dict[str, object]] = {}

    def scorer(name: str) -> Callable[..., dict[str, object]]:
        score: dict[str, object] = {"status": "failed", "scope": name, "checks": {}}
        scores[name] = score

        def assess(
            case: dict[str, object], observed: dict[str, object]
        ) -> dict[str, object]:
            assert "expected" in case
            assert observed == observation
            observed["extra"] = "mutated"
            case.clear()
            return score

        return assess

    for name in ("tools", "plan", "outcome", "claims"):
        monkeypatch.setitem(dispatch._SCORERS, name, scorer(name))
    slot = _slot(slots, "F04", driver)
    before = deepcopy(slot.case)
    result = dispatch.run_slot(slot, _runtime(RecordingProvider))
    assert result["status"] == status
    assert result["observation"] is observation
    assert observation["extra"] == "retained"
    assert slot.case == before
    for name, score in scores.items():
        assert _map(result["assessments"])[name] is score


@pytest.mark.parametrize(
    "report,execution,assessment",
    [
        ({"checks": {"guard": False}}, "completed", "failed"),
        ({"checks": {}}, "completed", "unassessed"),
        ({"checks": {"guard": 1}}, "failed", "failed"),
        ({"checks": []}, "failed", "failed"),
        ({"status": "failed", "checks": {"guard": True}}, "failed", "failed"),
        ({"status": "failed", "checks": {}}, "failed", "failed"),
        ({"status": "unassessed", "checks": {}}, "unassessed", "unassessed"),
    ],
)
def test_fixture_guards_preserve_report_and_execution(
    slots: list[EvaluationSlot],
    monkeypatch: pytest.MonkeyPatch,
    report: dict[str, object],
    execution: str,
    assessment: str,
) -> None:
    def evaluate(case: dict[str, object]) -> dict[str, object]:
        return report

    monkeypatch.setitem(dispatch._FIXTURES, "budget", evaluate)
    result = dispatch.run_slot(_slot(slots, "B01", "budget"), _runtime())
    assert result["report"] is report
    assert result["status"] == execution
    assert _map(_map(result["assessments"])["fixture"])["status"] == assessment


@pytest.mark.parametrize(
    "source", ["factory", "observer", "scorer", "fixture", "duplicate"]
)
def test_boundary_exceptions_are_static_and_redacted(
    slots: list[EvaluationSlot], monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    def fail(*args: object, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("PRIVATE_EXCEPTION_MARKER credential=hidden")

    def observe(*args: object, **kwargs: object) -> dict[str, object]:
        return {"status": "completed", "turns": []}

    slot = _slot(slots, "F04", "model")
    runtime = _runtime(RecordingProvider)
    monkeypatch.setattr(dispatch, "observe_model_case", observe)
    if source == "factory":
        runtime = _runtime(cast(Callable[[], LLMProvider], fail))
    elif source == "observer":
        monkeypatch.setattr(dispatch, "observe_model_case", fail)
    elif source == "scorer":
        monkeypatch.setitem(dispatch._SCORERS, "claims", fail)
    elif source == "fixture":
        slot = _slot(slots, "B01", "budget")
        monkeypatch.setitem(dispatch._FIXTURES, "budget", fail)
    else:
        slot = _slot(slots, "P05", "duplicate")
        runtime = replace(
            runtime,
            database_url="PRIVATE_DATABASE_MARKER",
            endpoint="PRIVATE_ENDPOINT_MARKER",
        )
        monkeypatch.setattr(dispatch, "evaluate_duplicate_case", fail)
    result = dispatch.run_slot(slot, runtime)
    assert result["status"] == "failed"
    observation = _map(result["observation"])
    assert observation["reason_code"] == "slot_execution_failed"
    assert observation["evidence_class"] == "unknown"
    assert observation["turns"] == observation["evidence_paths"] == []
    assert _map(_map(result["assessments"])["fixture"])["checks"] == {}
    assert "PRIVATE_" not in repr(result)
    assert "credential" not in repr(result)
    assert "traceback" not in repr(result)
    _assert_frame(result, slot)


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit])
@pytest.mark.parametrize("source", ["factory", "observer", "scorer", "fixture"])
def test_process_interrupts_propagate(
    slots: list[EvaluationSlot],
    monkeypatch: pytest.MonkeyPatch,
    interrupt: type[BaseException],
    source: str,
) -> None:
    def fail(*args: object, **kwargs: object) -> dict[str, object]:
        raise interrupt

    slot = _slot(slots, "F04", "model")
    runtime = _runtime(RecordingProvider)
    if source == "factory":
        runtime = _runtime(cast(Callable[[], LLMProvider], fail))
    elif source == "observer":
        monkeypatch.setattr(dispatch, "observe_model_case", fail)
    elif source == "scorer":
        monkeypatch.setitem(dispatch._SCORERS, "tools", fail)
    else:
        slot = _slot(slots, "B01", "budget")
        monkeypatch.setitem(dispatch._FIXTURES, "budget", fail)
    with pytest.raises(interrupt):
        dispatch.run_slot(slot, runtime)


@pytest.mark.parametrize(
    "condition", ["no_tool", "deterministic", "controlled_fixture", "unknown"]
)
def test_incompatible_route_never_calls_factory(
    slots: list[EvaluationSlot], condition: str
) -> None:
    calls: list[str] = []

    def factory() -> LLMProvider:
        calls.append("called")
        return RecordingProvider()

    slot = replace(_slot(slots, "F04", "model"), condition=condition)
    result = dispatch.run_slot(slot, _runtime(factory))
    assert result["status"] == "failed"
    assert _map(result["observation"])["reason_code"] == "slot_execution_failed"
    assert calls == []


def test_unknown_driver_fails_before_execution(slots: list[EvaluationSlot]) -> None:
    result = dispatch.run_slot(replace(slots[0], driver="unknown"), _runtime())
    assert result["status"] == "failed"


def test_elapsed_includes_factory_observer_and_scoring(
    slots: list[EvaluationSlot], monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [10.0]

    def factory() -> LLMProvider:
        clock[0] += 2
        return RecordingProvider()

    def observe(*args: object, **kwargs: object) -> dict[str, object]:
        clock[0] += 3
        return {"status": "completed", "turns": []}

    def score(*args: object, **kwargs: object) -> dict[str, object]:
        clock[0] += 5
        return {"status": "failed"}

    monkeypatch.setattr(dispatch, "monotonic", lambda: clock[0])
    monkeypatch.setattr(dispatch, "observe_model_case", observe)
    for name in ("tools", "plan", "outcome", "claims"):
        monkeypatch.setitem(dispatch._SCORERS, name, score)
    result = dispatch.run_slot(_slot(slots, "F04", "model"), _runtime(factory))
    assert result["elapsed_seconds"] == 25.0
    assert result["status"] == "completed"


def test_mutating_fixture_cannot_change_caller_inputs(
    slots: list[EvaluationSlot], monkeypatch: pytest.MonkeyPatch
) -> None:
    slot = _slot(slots, "B01", "budget")
    before = deepcopy(slot.case)

    def evaluate(case: dict[str, object]) -> dict[str, object]:
        _map(case["inputs"]).clear()
        _map(case["expected"]).clear()
        case.clear()
        return {"checks": {"guard": True}}

    monkeypatch.setitem(dispatch._FIXTURES, "budget", evaluate)
    result = dispatch.run_slot(slot, _runtime())
    assert result["status"] == "completed"
    assert slot.case == before


def test_mutating_observer_cannot_change_caller_inputs(
    slots: list[EvaluationSlot], monkeypatch: pytest.MonkeyPatch
) -> None:
    slot = _slot(slots, "F04", "model")
    before = deepcopy(slot.case)

    def observe(
        case: dict[str, object], *args: object, **kwargs: object
    ) -> dict[str, object]:
        _map(case["inputs"]).clear()
        case.clear()
        return {"status": "completed", "turns": []}

    monkeypatch.setattr(dispatch, "observe_model_case", observe)
    result = dispatch.run_slot(slot, _runtime(RecordingProvider))
    assert result["status"] == "completed"
    assert slot.case == before


def test_elapsed_includes_scoring_before_failure(
    slots: list[EvaluationSlot], monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [10.0]

    def observe(*args: object, **kwargs: object) -> dict[str, object]:
        clock[0] += 3
        return {"status": "completed", "turns": []}

    def score(*args: object, **kwargs: object) -> dict[str, object]:
        clock[0] += 7
        raise ValueError("PRIVATE_FAILURE_MARKER")

    monkeypatch.setattr(dispatch, "monotonic", lambda: clock[0])
    monkeypatch.setattr(dispatch, "observe_model_case", observe)
    monkeypatch.setitem(dispatch._SCORERS, "tools", score)
    result = dispatch.run_slot(
        _slot(slots, "F04", "model"), _runtime(RecordingProvider)
    )
    assert result["elapsed_seconds"] == 10.0
    assert result["status"] == "failed"
    assert "PRIVATE_FAILURE_MARKER" not in repr(result)
