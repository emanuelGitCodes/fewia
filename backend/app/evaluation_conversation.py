"""Run conversation-eval-v1 and emit hash-only observation records.

A record holds the tool trace, the validator verdict, usage, latency, and the
reply's SHA-256. It never holds the reply text, the model's raw text, or the
validator's unmatched tokens.
"""

from collections.abc import Callable, Iterator
from copy import deepcopy
from datetime import date
from time import perf_counter
from uuid import UUID

from app.agent import chat_loop
from app.agent.chat_context import MAX_HISTORY, _public_text, plan_ingredient_ids
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

GATES = frozenset(
    ("clean", "proposal", "tool_failed", "not_final", "planner", "no_tools")
    + ("clarification", "refusal", "incomplete", "limit", "planned_terminal")
    + ("discovery_terminal", "guardrail")
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
    for name, payload in payloads:
        got = _lookup(payload, gold.path)
        if (
            name == gold.tool
            and got is not _MISSING
            and got == gold.value
            and type(got) is type(gold.value)
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
        "latency_ms": latency_ms,
        "apply_error": apply_error,
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
    corpus: ConversationCorpus, profile: str, provider_for: ProviderFor
) -> Iterator[dict[str, object]]:
    """Yield one record per turn, for each scenario and each of three repeats."""
    for scenario in corpus.scenarios:
        for repeat in range(1, corpus.repeats + 1):
            yield from _run_scenario(scenario, repeat, profile, provider_for)
