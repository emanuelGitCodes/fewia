"""Run conversation-eval-v1.6and emit hash-only observation records.

A record holds the tool trace, the validator verdict, usage, latency, and the
reply's SHA-256. It never holds the reply text, the model's raw text, or the
validator's unmatched tokens.
"""

from collections.abc import Callable, Iterator
from copy import deepcopy
from datetime import date
from time import perf_counter
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from app.agent import chat_loop
from app.agent.catalog_tool import (
    CatalogToolError,
    execute_catalog_search,
    exhausted_page_arguments,
    page_arguments,
)
from app.agent.chat_context import MAX_HISTORY, _public_text, plan_ingredient_ids
from app.agent.chat_messages import is_guardrail_decline, last_what_if_recipe
from app.agent.grounding import REASON_CODES
from app.agent.proposal_tool import Propose
from app.agent.provider import LLMProvider
from app.domain.plan_proposal import ProposalInvalid, apply_operations, parse_operations
from app.domain.plan_revision import PlanRevisionInput
from app.evaluation_budget_inputs import fixture_budget
from app.evaluation_capture import CaptureProvider
from app.evaluation_conversation_corpus import (
    ConversationCorpus,
    Gold,
    Scenario,
)
from app.evaluation_purchase import claims_purchase

GATES = frozenset(
    ("clean", "proposal", "tool_failed", "not_final", "planner", "no_tools")
    + ("clarification", "refusal", "incomplete", "limit", "planned_terminal")
    + ("discovery_terminal", "guardrail", "saved_plan_read")
    + ("swap_not_saved",)
)
REASONS = REASON_CODES
_USAGE_KEYS = (
    ("input", "inputTokens"),
    ("output", "outputTokens"),
    ("cache_read", "cacheReadInputTokens"),
    ("cache_write", "cacheWriteInputTokens"),
)
_MISSING = object()
ProviderFor = Callable[[Scenario, int, int], LLMProvider]


class _SelectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ScenarioRepeatSelection(_SelectionModel):
    scenario_id: StrictStr
    repeats: Annotated[list[StrictInt], Field(min_length=1)]


class ConversationSelection(_SelectionModel):
    scenarios: Annotated[list[ScenarioRepeatSelection], Field(min_length=1)]


def normalize_selection(
    corpus: ConversationCorpus, selection: ConversationSelection
) -> ConversationSelection:
    """Validate a selection and order it by corpus scenario and repeat."""
    available = {scenario.id for scenario in corpus.scenarios}
    selected: dict[str, list[int]] = {}
    for item in selection.scenarios:
        if item.scenario_id in selected or item.scenario_id not in available:
            raise ValueError("invalid conversation selection")
        if len(set(item.repeats)) != len(item.repeats):
            raise ValueError("invalid conversation selection")
        if any(repeat < 1 or repeat > corpus.repeats for repeat in item.repeats):
            raise ValueError("invalid conversation selection")
        selected[item.scenario_id] = sorted(item.repeats)
    return ConversationSelection(
        scenarios=[
            ScenarioRepeatSelection(
                scenario_id=scenario.id,
                repeats=selected[scenario.id],
            )
            for scenario in corpus.scenarios
            if scenario.id in selected
        ]
    )


def logical_chat_turn_count(
    corpus: ConversationCorpus, selection: ConversationSelection | None = None
) -> int:
    """Count user turns across the selected scenarios and repeats."""
    turns_by_id = {scenario.id: len(scenario.turns) for scenario in corpus.scenarios}
    if selection is None:
        return sum(turns_by_id.values()) * corpus.repeats
    return sum(
        turns_by_id[item.scenario_id] * len(item.repeats)
        for item in selection.scenarios
    )


def _lookup(payload: object, path: str) -> object:
    for part in path.split("."):
        if isinstance(payload, list) and part.isdigit() and int(part) < len(payload):
            payload = payload[int(part)]
        elif isinstance(payload, dict) and part in payload:
            payload = payload[part]
        else:
            return _MISSING
    return payload


def _payloads(
    result: dict[str, object], capture: CaptureProvider
) -> list[tuple[object, object]]:
    """Pair each tool result the model saw with the tool that produced it."""
    trace = result.get("tool_trace")
    names = {
        entry.get("tool_use_id"): entry.get("tool")
        for entry in (trace if isinstance(trace, list) else [])
        if isinstance(entry, dict)
    }
    found: list[tuple[object, object]] = []
    for item in capture.tool_results:
        content = item.get("content")
        first = content[0] if isinstance(content, list) and content else None
        if isinstance(first, dict):
            found.append((names.get(item.get("toolUseId")), first.get("json")))
    return found


def _present(gold: Gold, payloads: list[tuple[object, object]]) -> bool:
    expected: object = gold.value
    if gold.reference:
        try:
            expected = _lookup(execute_catalog_search(gold.input), gold.path)
        except CatalogToolError:
            return False
        if expected is _MISSING:
            return False
    for name, payload in payloads:
        got = _lookup(payload, gold.path)
        if (
            name == gold.tool
            and got is not _MISSING
            and got == expected
            and type(got) is type(expected)
        ):
            return True
    return False


def _usage(raw: object) -> dict[str, int | None]:
    source = raw if isinstance(raw, dict) else None
    usage: dict[str, int | None] = {}
    for name, key in _USAGE_KEYS:
        value = None if source is None else source.get(key, 0)
        usage[name] = value if type(value) is int else None
    return usage


def _observation(
    scenario: Scenario,
    repeat: int,
    index: int,
    profile: str,
    result: dict[str, object] | None,
    capture: CaptureProvider,
    latency_ms: int,
    apply_error: str | None = None,
) -> dict[str, object]:
    gold = scenario.turns[index - 1].expect.gold
    answer = None if result is None else result.get("answer")
    record: dict[str, object] = {
        "scenario_id": scenario.id,
        "repeat": repeat,
        "turn": index,
        "profile": profile,
        "status": "failed",
        "reply_source": "none",
        "reply_sha256": None,
        "gate": None,
        "verdict": {"ok": None, "reasons": [], "unmatched_count": 0},
        "proposal": False,
        "tools": [],
        "facts_present": [False] * len(gold),
        "usage": _usage(None),
        "provider_requests": capture.provider_calls,
        "latency_ms": latency_ms,
        "apply_error": apply_error,
        "purchase_signals": {
            "observed": result is not None
            and not capture.capture_incomplete
            and capture.invalid_responses == 0,
            "unoffered_tool_requests": capture.unoffered_tool_requests,
            "purchase_named_tool_requests": capture.purchase_named_tool_requests,
            "reply_claim": isinstance(answer, str) and claims_purchase(answer),
            "model_claim": capture.model_purchase_claim,
        },
    }
    if result is None:
        return record
    check = result.get("reply_check")
    check = check if isinstance(check, dict) else {}
    gate = check.get("gate")
    gate = gate if gate in GATES else None
    reasons, unmatched = check.get("reasons"), check.get("unmatched")
    trace = result.get("tool_trace")
    payloads = _payloads(result, capture)
    record.update(
        status=str(result.get("status")),
        reply_source=str(result.get("reply_source")),
        reply_sha256=result.get("reply_sha256"),
        gate=gate,
        verdict={
            "ok": check.get("ok") is True if gate == "clean" else None,
            "reasons": [r for r in reasons if r in REASONS]
            if gate == "clean" and isinstance(reasons, list)
            else [],
            "unmatched_count": len(unmatched) if isinstance(unmatched, list) else 0,
        },
        proposal=result.get("proposal_id") is not None,
        tools=[
            {
                "name": entry.get("tool"),
                "outcome": entry.get("outcome"),
                "inputs": entry.get("inputs"),
            }
            for entry in (trace if isinstance(trace, list) else [])
            if isinstance(entry, dict)
        ],
        facts_present=[_present(item, payloads) for item in gold],
        usage=_usage(result.get("usage")),
    )
    return record


def _stub(pending: list[list[dict[str, object]]], label: str) -> Propose:
    def propose(operations: list[dict[str, object]]) -> str:
        pending[:] = [deepcopy(operations)]
        return label

    return propose


def _run_scenario(
    scenario: Scenario, repeat: int, profile: str, provider_for: ProviderFor
) -> Iterator[dict[str, object]]:
    inputs = scenario.inputs
    budget = fixture_budget(inputs.model_dump())
    period = date.fromisoformat(inputs.budget_period)
    plan = PlanRevisionInput(
        id=UUID(int=repeat), snapshot=scenario.plan.model_copy(deep=True)
    )
    pending: list[list[dict[str, object]]] = []
    history: list[dict[str, str]] = []
    previous: dict[str, object] | None = None
    previous_ids: list[str] | None = None
    previous_search: dict[str, object] | None = None
    previous_exhausted_search: dict[str, object] | None = None
    previous_what_if: str | None = None
    for index, turn in enumerate(scenario.turns, start=1):
        apply_error: str | None = None
        if turn.apply_proposal_before:
            if not pending:
                apply_error = "missing"
            else:
                try:
                    snapshot = apply_operations(
                        plan.snapshot, parse_operations(pending[0])
                    )
                    plan = PlanRevisionInput(
                        id=UUID(int=repeat * 100 + index), snapshot=snapshot
                    )
                except ProposalInvalid:
                    apply_error = "invalid"
            pending.clear()
        capture = CaptureProvider(provider_for(scenario, repeat, index))
        result: dict[str, object] | None = None
        started = perf_counter()
        try:
            result = chat_loop.run_chat(
                capture,
                turn.user,
                budget,
                period,
                user_id=inputs.user_id,
                spending_source="fixture",
                previous_request=previous,
                previous_ingredient_ids=previous_ids,
                previous_search=previous_search,
                previous_exhausted_search=previous_exhausted_search,
                previous_what_if_recipe=previous_what_if,
                history=history or None,
                plan_cap_cents=inputs.plan_cap_cents,
                plan_revision=plan,
                observe_terminal_tool_results=capture.observe_terminal_tool_results,
                model_prose=True,
                propose=_stub(pending, f"eval-{scenario.id}-{repeat}-{index}"),
            )
        except Exception:  # noqa: BLE001
            result = None
        latency_ms = round((perf_counter() - started) * 1000)
        yield _observation(
            scenario, repeat, index, profile, result, capture, latency_ms, apply_error
        )
        if result is None:
            return
        previous_search = page_arguments(result.get("next_search"))
        previous_exhausted_search = exhausted_page_arguments(
            result.get("exhausted_search")
        )
        previous_what_if = last_what_if_recipe(result)
        if is_guardrail_decline(result):
            pending.clear()
            continue
        ids = plan_ingredient_ids(result.get("plan"))
        previous_ids = ids if ids is not None else previous_ids
        request, answer = result.get("request"), result.get("answer")
        previous = request if isinstance(request, dict) else previous
        if _public_text(answer):
            history += [
                {"role": "user", "text": turn.user},
                {"role": "assistant", "text": answer},
            ]
            history = history[-MAX_HISTORY:]


def run_conversation_suite(
    corpus: ConversationCorpus,
    profile: str,
    provider_for: ProviderFor,
    *,
    selection: ConversationSelection | None = None,
) -> Iterator[dict[str, object]]:
    """Yield one record per turn and selected repeat."""
    selected_repeats = (
        {item.scenario_id: item.repeats for item in selection.scenarios}
        if selection is not None
        else None
    )
    for scenario in corpus.scenarios:
        repeats = (
            range(1, corpus.repeats + 1)
            if selected_repeats is None
            else selected_repeats.get(scenario.id, [])
        )
        for repeat in repeats:
            yield from _run_scenario(scenario, repeat, profile, provider_for)
