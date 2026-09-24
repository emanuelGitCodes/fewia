from __future__ import annotations

import copy
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any, Literal, cast

import pytest

from app.agent.chat_answer import CLARIFY_ANSWER, render_public_answer
from app.agent.chat_context import MAX_HISTORY, MAX_MESSAGE_LEN
from app.agent.chat_loop import SYSTEM_PROMPT
from app.agent.planning_tool import TOOL_NAME, execute_plan
from app.domain.catalog import CATALOG_VERSION
from app.evaluation_budget_inputs import fixture_budget
from app.evaluation_model import observe_model_case

CORPUS_PATH = Path(__file__).parent / "evaluation" / "scenarios.json"
PERIOD = date(2026, 9, 1)
MODEL_ID = "eval-fake-v1"
SECRET = "do-not-echo-raw-input"
MODEL_PROSE = "Choose a supported meal."
MODEL_CASE_IDS = ("F01", "F02", "F04", "F05", "X02", "X03", "X04", "A01", "A03", "A04")
SECRETS_REFUSAL = (
    "I cannot provide credentials or raw bank records. "
    "I can help plan meals using the budget summary."
)
EXTERNAL_REFUSAL = (
    "I cannot open external links or place orders. I can help prepare a grocery plan."
)
Evidence = Literal["deterministic_fake_provider", "real_bedrock"]


class FakeLLM:
    def __init__(self, replies: list[dict[str, object] | BaseException]) -> None:
        self._replies = list(replies)
        self.requests: list[dict[str, object]] = []

    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        snapshot = copy.deepcopy(messages)
        self.requests.append(
            {"system": system_prompt, "messages": snapshot, "tools": tools}
        )
        if not self._replies:
            raise AssertionError("unexpected provider call")
        reply = self._replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply


def _load_case(case_id: str) -> dict[str, object]:
    payload: object = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    rows = payload["scenarios"]
    assert isinstance(rows, list)
    for item in rows:
        assert isinstance(item, dict)
        row = cast(dict[str, object], item)
        if row.get("id") == case_id:
            return copy.deepcopy(row)
    raise AssertionError(f"missing case {case_id}")


def _scenario_ids() -> tuple[str, ...]:
    payload: object = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    rows = payload["scenarios"]
    assert isinstance(rows, list)
    ids: list[str] = []
    for item in rows:
        assert isinstance(item, dict)
        case_id = item.get("id")
        assert type(case_id) is str and case_id != ""
        ids.append(case_id)
    return tuple(ids)


def _unsupported_case_ids() -> tuple[str, ...]:
    return tuple(
        case_id for case_id in _scenario_ids() if case_id not in MODEL_CASE_IDS
    )


def _patch_monotonic(monkeypatch: pytest.MonkeyPatch) -> None:
    ticks = {"now": 10.0}

    def monotonic() -> float:
        ticks["now"] += 0.25
        return ticks["now"]

    monkeypatch.setattr("app.evaluation_model.time.monotonic", monotonic)


def _assert_elapsed(turn: object) -> None:
    assert isinstance(turn, dict)
    elapsed = turn["elapsed_seconds"]
    assert type(elapsed) is float
    assert elapsed > 0


def _blob(value: object) -> str:
    return json.dumps(value, default=str)


def _hexdigest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _plan(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "meals": [{"recipe_id": "chicken_tacos", "servings": 2}],
        "budget_period": PERIOD.isoformat(),
        "diet": "omnivore",
        "pantry_ingredients": [],
        "ingredient_exclusions": [],
    }
    values.update(overrides)
    return values


def _reply(
    content: list[dict[str, object]],
    stop: str,
    *,
    omit_usage: bool = False,
) -> dict[str, object]:
    body: dict[str, object] = {
        "output": {"message": {"role": "assistant", "content": content}},
        "stopReason": stop,
    }
    if not omit_usage:
        body["usage"] = {"inputTokens": 1, "outputTokens": 1}
    return body


def _tool_block(tool_id: str, payload: dict[str, object]) -> dict[str, object]:
    return {
        "toolUse": {
            "toolUseId": tool_id,
            "name": TOOL_NAME,
            "input": payload,
        }
    }


def _text_block(text: str) -> dict[str, object]:
    return {"text": text}


def _tool_then_text(
    tool_id: str,
    payload: dict[str, object],
    answer: str,
    *,
    omit_usage: bool = False,
) -> list[dict[str, object] | BaseException]:
    return [
        _reply([_tool_block(tool_id, payload)], "tool_use", omit_usage=omit_usage),
        _reply([_text_block(answer)], "end_turn", omit_usage=omit_usage),
    ]


def _observe(
    case: dict[str, object],
    replies: list[dict[str, object] | BaseException],
    *,
    evidence_class: Evidence = "deterministic_fake_provider",
    model_id: str = MODEL_ID,
) -> tuple[dict[str, object], FakeLLM]:
    provider = FakeLLM(replies)
    report = observe_model_case(
        case,
        provider,
        evidence_class=evidence_class,
        model_id=model_id,
    )
    return report, provider


def _turn_result(turn: object) -> dict[str, object]:
    assert isinstance(turn, dict)
    payload = turn.get("result")
    assert isinstance(payload, dict)
    return cast(dict[str, object], payload)


def _context(messages: object, index: int = -1) -> dict[str, object]:
    assert isinstance(messages, list)
    last = messages[index]
    assert isinstance(last, dict)
    content = last["content"]
    assert isinstance(content, list)
    parsed: object = json.loads(cast(str, content[0]["text"]))
    assert isinstance(parsed, dict)
    return cast(dict[str, object], parsed)


def test_f05_multi_turn_returns_request_and_public_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_monotonic(monkeypatch)
    case = _load_case("F05")
    first = _plan()
    second = _plan(meals=[{"recipe_id": "chicken_tacos", "servings": 4}])
    replies = _tool_then_text("t1", first, "Here is a labeled estimate.")
    replies.extend(_tool_then_text("t2", second, "Updated to four servings."))
    report, provider = _observe(case, replies)
    assert report["case_id"] == "F05"
    assert report["status"] == "completed"
    assert report["reason"] is None
    assert report["catalog_version"] == CATALOG_VERSION
    turns = report["turns"]
    assert isinstance(turns, list)
    assert len(turns) == 2
    first_result = _turn_result(turns[0])
    second_result = _turn_result(turns[1])
    inputs = case["inputs"]
    assert isinstance(inputs, dict)
    budget = fixture_budget(cast(dict[str, object], inputs))
    first_expected = execute_plan(first, budget, PERIOD)
    second_expected = execute_plan(second, budget, PERIOD)
    first_answer = render_public_answer(first_expected)
    second_answer = render_public_answer(second_expected)
    assert first_result["request"] == first_expected["request"]
    assert second_result["request"] == second_expected["request"]
    assert first_result["answer"] == first_answer
    assert second_result["answer"] == second_answer
    assert first_result["answer"] != "Here is a labeled estimate."
    assert second_result["answer"] != "Updated to four servings."
    assert report["metrics_status"] == "unassessed"
    _assert_elapsed(turns[0])
    _assert_elapsed(turns[1])
    assert len(provider.requests) == 4
    follow = provider.requests[2]["messages"]
    assert isinstance(follow, list)
    first_user = case["messages"]
    assert isinstance(first_user, list)
    opening = first_user[0]
    assert isinstance(opening, dict)
    first_text = opening["content"]
    assert follow[0] == {"role": "user", "content": [{"text": first_text}]}
    assert follow[1] == {
        "role": "assistant",
        "content": [{"text": first_answer}],
    }
    assert len(follow) == 3
    assert follow[2]["role"] == "user"
    previous = _context(follow)["previous_request"]
    assert previous == first_result["request"]
    assert SECRET not in _blob(report)
    assert "snapshot" not in _blob(report)


def test_history_stays_within_max_history() -> None:
    case = _load_case("F01")
    texts = [f"turn-{index}" for index in range(6)]
    case["messages"] = [{"role": "user", "content": text} for text in texts]
    replies: list[dict[str, object] | BaseException] = [
        _reply([_text_block(f"answer-{index}")], "end_turn") for index in range(6)
    ]
    report, provider = _observe(case, replies)
    assert report["status"] == "completed"
    assert len(provider.requests) == 6
    last_messages = provider.requests[-1]["messages"]
    assert isinstance(last_messages, list)
    public = last_messages[:-1]
    assert len(public) == MAX_HISTORY
    assert public[0] == {"role": "user", "content": [{"text": "turn-1"}]}
    assert "turn-0" not in _blob(public)
    assert public[-1] == {
        "role": "assistant",
        "content": [{"text": CLARIFY_ANSWER}],
    }
    assert "answer-4" not in _blob(public)


@pytest.mark.parametrize("case_id", MODEL_CASE_IDS)
def test_supported_id_observes_simple_final_response(
    case_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_monotonic(monkeypatch)
    case = _load_case(case_id)
    messages = case["messages"]
    assert isinstance(messages, list)
    replies = [_reply([_text_block(MODEL_PROSE)], "end_turn") for _ in messages]
    report, provider = _observe(case, replies)
    assert report["case_id"] == case_id
    assert report["status"] == "completed"
    assert report["reason"] is None
    assert len(provider.requests) == len(messages)
    turns = report["turns"]
    assert isinstance(turns, list)
    assert len(turns) == len(messages)
    for turn in turns:
        _assert_elapsed(turn)
        result = _turn_result(turn)
        assert result["answer"] == CLARIFY_ANSWER
        assert result["answer"] != MODEL_PROSE
        assert result["status"] == "clarification"
    assert report["metrics_status"] == "unassessed"


@pytest.mark.parametrize("case_id", _unsupported_case_ids())
def test_unsupported_id_does_not_call_provider(case_id: str) -> None:
    case = _load_case(case_id)
    report, provider = _observe(case, [])
    assert report["case_id"] == case_id
    assert report["status"] == "unassessed"
    assert report["reason"] == "unsupported_scenario"
    assert report["turns"] == []
    assert provider.requests == []
    assert report["metrics_status"] == "unassessed"


def test_malformed_input_does_not_call_provider() -> None:
    kinds = (
        "no_messages",
        "empty_messages",
        "assistant_role",
        "blank_content",
        "overlong",
        "secret_period",
        "missing_inputs",
    )
    for kind in kinds:
        case = _load_case("X02")
        if kind == "no_messages":
            case.pop("messages")
        elif kind == "empty_messages":
            case["messages"] = []
        elif kind == "assistant_role":
            case["messages"] = [{"role": "assistant", "content": "Plan meals."}]
        elif kind == "blank_content":
            case["messages"] = [{"role": "user", "content": "   "}]
        elif kind == "overlong":
            case["messages"] = [
                {"role": "user", "content": "x" * (MAX_MESSAGE_LEN + 1)}
            ]
        elif kind == "secret_period":
            inputs = case["inputs"]
            assert isinstance(inputs, dict)
            inputs["budget_period"] = SECRET
            inputs["monthly_limit_cents"] = SECRET
        else:
            case.pop("inputs")
        report, provider = _observe(case, [])
        assert report["status"] == "invalid_input"
        assert report["reason"] == "invalid_input"
        assert report["turns"] == []
        assert provider.requests == []
        assert SECRET not in _blob(report)


def test_unhashable_evidence_class_is_invalid_without_leak() -> None:
    case = _load_case("X02")
    provider = FakeLLM([])
    report = observe_model_case(
        case,
        provider,
        evidence_class=cast(Any, [SECRET]),
        model_id=SECRET,
    )
    blob = _blob(report)
    assert report["case_id"] == "invalid_case"
    assert report["status"] == "invalid_input"
    assert report["reason"] == "invalid_input"
    assert "evidence_class" not in report
    assert "model_id" not in report
    assert "model_hash" not in report
    assert SECRET not in blob
    assert provider.requests == []


def test_invalid_metadata_does_not_leak_strings() -> None:
    case = _load_case("F01")
    provider = FakeLLM([])
    report = observe_model_case(
        case,
        provider,
        evidence_class=cast(Any, SECRET),
        model_id=f"  {SECRET}  ",
    )
    blob = _blob(report)
    assert report["status"] == "invalid_input"
    assert "evidence_class" not in report
    assert "model_id" not in report
    assert SECRET not in blob
    assert provider.requests == []


def test_provider_exception_is_partial_without_sentinel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_monotonic(monkeypatch)
    case = _load_case("F05")
    first = _plan()
    replies = _tool_then_text("t1", first, "Here is a labeled estimate.")
    replies.append(RuntimeError(SECRET))
    report, provider = _observe(case, replies)
    assert report["status"] == "partial"
    assert report["reason"] == "provider_unavailable"
    turns = report["turns"]
    assert isinstance(turns, list)
    assert len(turns) == 2
    first_turn = turns[0]
    failed = turns[1]
    assert isinstance(first_turn, dict)
    assert isinstance(failed, dict)
    assert first_turn["status"] == "completed"
    kept = _turn_result(first_turn)
    inputs = case["inputs"]
    assert isinstance(inputs, dict)
    budget = fixture_budget(cast(dict[str, object], inputs))
    assert kept["request"] == execute_plan(first, budget, PERIOD)["request"]
    assert failed["status"] == "failed"
    assert failed["reason"] == "provider_unavailable"
    assert failed.get("usage") is None
    _assert_elapsed(first_turn)
    _assert_elapsed(failed)
    assert SECRET not in _blob(report)
    assert len(provider.requests) == 3


def test_missing_token_usage_remains_none() -> None:
    case = _load_case("X02")
    replies = [
        _reply(
            [_text_block(MODEL_PROSE)],
            "end_turn",
            omit_usage=True,
        )
    ]
    report, provider = _observe(case, replies)
    assert report["status"] == "completed"
    turns = report["turns"]
    assert isinstance(turns, list)
    result = _turn_result(turns[0])
    assert result["usage"] is None
    assert result["answer"] == CLARIFY_ANSWER
    assert result["answer"] != MODEL_PROSE
    assert result["status"] == "clarification"
    assert len(provider.requests) == 1


def test_model_and_prompt_hashes() -> None:
    case = _load_case("X02")
    replies = [_reply([_text_block("Choose a supported meal.")], "end_turn")]
    report, _provider = _observe(case, replies, evidence_class="real_bedrock")
    assert report["model_id"] == MODEL_ID
    assert report["prompt_hash"] == _hexdigest(SYSTEM_PROMPT)
    assert report["evidence_class"] == "real_bedrock"
    assert report["metrics_status"] == "unassessed"


def test_gold_changes_do_not_affect_observation() -> None:
    case = _load_case("F01")
    first = _plan(meals=[{"recipe_id": "bean_tacos", "servings": 2}])
    second = _plan(
        meals=[{"recipe_id": "bean_tacos", "servings": 2}],
        pantry_ingredients=["black_beans"],
    )
    replies = _tool_then_text("p1", first, "Bean taco estimate.")
    replies.extend(_tool_then_text("p2", second, "Black beans are in the pantry."))
    baseline, _provider = _observe(case, list(replies))
    mutated = _load_case("F01")
    expected = mutated["expected"]
    assert isinstance(expected, dict)
    expected["total_cents"] = 1
    expected["accepted"] = False
    expected["lines"] = []
    changed, _ignored = _observe(mutated, list(replies))
    for report in (baseline, changed):
        assert report["metrics_status"] == "unassessed"
        turns = report["turns"]
        assert isinstance(turns, list)
        for turn in turns:
            assert isinstance(turn, dict)
            turn.pop("elapsed_seconds", None)
    assert baseline == changed
    last = _turn_result(changed["turns"][-1])
    plan = last["plan"]
    assert isinstance(plan, dict)
    assert plan["total_cents"] != 1
    assert last["request"] is not None
    assert last["answer"] != "Black beans are in the pantry."
    assert last["answer"] != "Bean taco estimate."


def test_report_does_not_claim_snapshots() -> None:
    case = _load_case("X02")
    replies = [_reply([_text_block("Choose a supported meal.")], "end_turn")]
    report, _provider = _observe(case, replies)
    blob = _blob(report)
    assert "snapshot" not in blob
    assert report["metrics_status"] == "unassessed"
    assert report.get("snapshots_created") is None


def test_observe_passes_input_plan_cap_for_a01() -> None:
    case = _load_case("A01")
    original = copy.deepcopy(case)
    replies = [_reply([_text_block(MODEL_PROSE)], "end_turn")]
    report, provider = _observe(case, replies)
    assert report["status"] == "completed"
    assert len(provider.requests) == 1
    context = _context(provider.requests[0]["messages"])
    inputs = case["inputs"]
    assert isinstance(inputs, dict)
    budget = fixture_budget(cast(dict[str, object], inputs))
    assert context["plan_cap_cents"] == 1
    assert context["budget"]["available_cents"] == budget.available_cents
    assert context["budget"]["available_cents"] == 1
    messages = provider.requests[0]["messages"]
    assert isinstance(messages, list)
    last = messages[-1]
    assert isinstance(last, dict)
    content = last["content"]
    assert isinstance(content, list)
    users = case["messages"]
    assert isinstance(users, list)
    opening = users[0]
    assert isinstance(opening, dict)
    assert content[-1] == {"text": opening["content"]}
    assert case == original
    assert "When plan_cap_cents is an integer" in SYSTEM_PROMPT
    assert "MUST NOT set the request cap to the available budget" in SYSTEM_PROMPT


@pytest.mark.parametrize(
    ("case_id", "payload", "answer"),
    (
        ("A03", '{"refusal":"secrets"}', SECRETS_REFUSAL),
        ("A04", '{"refusal":"external_url"}', EXTERNAL_REFUSAL),
    ),
)
def test_observe_typed_refusal_json(
    case_id: str,
    payload: str,
    answer: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_monotonic(monkeypatch)
    case = _load_case(case_id)
    replies = [_reply([_text_block(payload)], "end_turn")]
    report, provider = _observe(case, replies)
    assert report["case_id"] == case_id
    assert report["status"] == "completed"
    assert report["reason"] is None
    assert report["evidence_class"] == "deterministic_fake_provider"
    assert report["metrics_status"] == "unassessed"
    assert len(provider.requests) == 1
    turns = report["turns"]
    assert isinstance(turns, list)
    assert len(turns) == 1
    _assert_elapsed(turns[0])
    result = _turn_result(turns[0])
    assert result["answer"] == answer
    assert result["status"] == "clarification"
    assert result["plan"] is None
    assert result["request"] is None
    assert result["evidence_id"] is None
    assert result["evidence_revision_id"] is None
    assert result["tool_trace"] == []
    assert result["model_turns"] == 1
    assert result["planner_revisions"] == 0
    blob = _blob(report)
    assert SECRET not in blob
    assert "snapshot" not in blob


def test_malformed_refusal_json_is_generic_clarification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_monotonic(monkeypatch)
    case = _load_case("A03")
    replies = [_reply([_text_block('{"refusal":"secrets"')], "end_turn")]
    report, provider = _observe(case, replies)
    assert report["status"] == "completed"
    assert report["metrics_status"] == "unassessed"
    assert len(provider.requests) == 1
    result = _turn_result(report["turns"][0])
    assert result["answer"] == CLARIFY_ANSWER
    assert result["answer"] != SECRETS_REFUSAL
    assert result["status"] == "clarification"
    assert result["plan"] is None
    assert result["tool_trace"] == []


@pytest.mark.parametrize("case_id", ("F02", "F05"))
def test_observe_null_plan_cap_stays_none(case_id: str) -> None:
    case = _load_case(case_id)
    users = case["messages"]
    assert isinstance(users, list)
    replies = [_reply([_text_block(MODEL_PROSE)], "end_turn") for _ in users]
    _report, provider = _observe(case, replies)
    inputs = case["inputs"]
    assert isinstance(inputs, dict)
    budget = fixture_budget(cast(dict[str, object], inputs))
    assert len(provider.requests) == len(users)
    for request in provider.requests:
        context = _context(request["messages"])
        assert context["plan_cap_cents"] is None
        assert context["budget"]["available_cents"] == budget.available_cents
        assert context["budget"]["available_cents"] == 10_000


@pytest.mark.parametrize("cap", [True, False, -1, "1", SECRET])
def test_invalid_plan_cap_does_not_call_provider(cap: object) -> None:
    case = _load_case("A01")
    inputs = case["inputs"]
    assert isinstance(inputs, dict)
    inputs["plan_cap_cents"] = cap
    report, provider = _observe(case, [])
    assert report["status"] == "invalid_input"
    assert report["reason"] == "invalid_input"
    assert report["turns"] == []
    assert provider.requests == []
    assert SECRET not in _blob(report)
