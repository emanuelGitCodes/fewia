from dataclasses import asdict
from typing import Literal, cast

from app.agent.chat_context import MAX_HISTORY
from app.agent.provider import LLMProvider
from app.evaluation_adversarial import (
    ScenarioProvider,
    sanitize_public,
    scenario_markers,
)
from app.evaluation_baseline_response import BASELINE_SYSTEM_PROMPT
from app.evaluation_inputs import prepare_case
from app.evaluation_manifest import _MODEL_ID, _hash, catalog_snapshot
from app.evaluation_no_tool_turn import observe_no_tool_turn


def observe_no_tool_case(
    case: dict[str, object],
    provider: LLMProvider,
    *,
    evidence_class: Literal["deterministic_fake_provider", "real_bedrock"],
    model_id: str,
) -> dict[str, object]:
    turns: list[dict[str, object]] = []
    observation: dict[str, object] = {
        "case_id": None,
        "condition": "no_tool",
        "status": "failed",
        "model_id": None,
        "evidence_class": None,
        "evidence_paths": [],
        "turns": turns,
        "snapshots": [],
        "injection_applied": False,
        "injected_text_hash": None,
        "system_prompt_hash": _hash(BASELINE_SYSTEM_PROMPT),
    }
    if (
        type(model_id) is not str
        or _MODEL_ID.fullmatch(model_id) is None
        or evidence_class not in ("deterministic_fake_provider", "real_bedrock")
    ):
        observation["reason"] = "invalid_configuration"
        return observation
    observation.update(model_id=model_id, evidence_class=evidence_class)
    markers: tuple[str, ...] = ()
    try:
        markers = scenario_markers(case) if type(case) is dict else ()
        context = prepare_case(case)
        scenario = ScenarioProvider(provider, case)
    except (TypeError, ValueError, RecursionError, OverflowError):
        observation["reason"] = "invalid_inputs"
        return cast(dict[str, object], sanitize_public(observation, markers))
    catalog = catalog_snapshot()
    facts: dict[str, object] = asdict(context.budget)
    facts["warnings"] = list(context.budget.warnings)
    facts.update(messages=list(context.messages), period=context.period.isoformat())
    facts["plan_cap_cents"] = context.plan_cap_cents
    observation.update(
        case_id=context.case_id,
        catalog_version=catalog["version"],
        catalog_hash=_hash(catalog),
        task_facts_hash=_hash(facts),
    )
    history: list[dict[str, str]] = []
    previous: dict[str, object] | None = None
    for message in context.messages:
        turn = observe_no_tool_turn(
            context,
            message,
            scenario,
            catalog=catalog,
            markers=markers,
            history=history,
            previous_request=previous,
        )
        turns.append(turn)
        if turn["status"] != "completed":
            observation["reason"] = turn["reason"]
            break
        result = cast(dict[str, object], turn["result"])
        request = result["request"]
        if isinstance(request, dict):
            previous = request
        history.extend(
            [
                {"role": "user", "text": message},
                {"role": "assistant", "text": cast(str, result["answer"])},
            ]
        )
        history = history[-MAX_HISTORY:]
    observation.update(
        status=(
            "completed"
            if len(turns) == len(context.messages)
            and all(t["status"] == "completed" for t in turns)
            else "partial"
            if any(t["status"] == "completed" for t in turns)
            else "failed"
        ),
        injection_applied=scenario.injection_applied,
        injected_text_hash=scenario.injected_text_hash,
        evidence_paths=[
            "model_only" if evidence_class == "real_bedrock" else evidence_class
        ]
        if any(cast(int, t["provider_calls"]) > 0 for t in turns)
        else [],
    )
    return cast(dict[str, object], sanitize_public(observation, markers))
