from contextlib import AbstractContextManager
from types import TracebackType
from typing import Literal, cast

from app.agent import chat_loop
from app.agent.chat_context import MAX_HISTORY, _public_text
from app.agent.provider import LLMProvider
from app.domain.catalog import CATALOG_VERSION
from app.evaluation_adversarial import (
    ScenarioProvider,
    sanitize_public,
    scenario_markers,
)
from app.evaluation_capture import CaptureProvider
from app.evaluation_evidence import EvaluationEvidence
from app.evaluation_inputs import prepare_case
from app.evaluation_manifest import _MODEL_ID, _hash, _validate_config
from app.evaluation_model_turn import observe_model_turn


class _EvidenceErrorBoundary(AbstractContextManager["_EvidenceErrorBoundary"]):
    failed: bool = False

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        self.failed = isinstance(exception, Exception)
        return self.failed


def observe_model_case(
    case: dict[str, object],
    provider: LLMProvider,
    *,
    evidence_class: Literal["deterministic_fake_provider", "real_bedrock"],
    model_id: str,
) -> dict[str, object]:
    turns: list[dict[str, object]] = []
    paths: list[str] = []
    snapshots: list[dict[str, object]] = []
    observation: dict[str, object] = {
        "case_id": "invalid_case",
        "condition": "tool_enabled",
        "status": "failed",
        "reason": "invalid_input",
        "model_id": None,
        "evidence_class": None,
        "injected_text_hash": None,
        "evidence_paths": paths,
        "turns": turns,
        "snapshots": snapshots,
        "system_prompt_hash": _hash(chat_loop.SYSTEM_PROMPT),
        "catalog_version": CATALOG_VERSION,
        "injection_applied": False,
    }
    try:
        if (
            type(model_id) is not str
            or _MODEL_ID.fullmatch(model_id) is None
            or evidence_class not in ("deterministic_fake_provider", "real_bedrock")
        ):
            return observation
        context = prepare_case(case)
        _validate_config(cast(dict[str, object], case.get("model_config", {})))
        markers = scenario_markers(case)
        facts: dict[str, object] = {
            "id": context.case_id,
            "messages": list(context.messages),
            "inputs": context.inputs,
        }
        if sanitize_public(facts, markers) != facts:
            return observation
        scenario = ScenarioProvider(provider, case, markers)
    except (TypeError, ValueError, OverflowError, RecursionError):
        return observation
    observation.update(
        case_id=context.case_id,
        model_id=model_id,
        evidence_class=evidence_class,
        reason=None,
    )
    history: list[dict[str, str]] = []
    previous: dict[str, object] | None = None
    store: EvaluationEvidence | None = None
    with _EvidenceErrorBoundary() as evidence:
        store = EvaluationEvidence(context)
        with store:
            paths.append("local_sqlite")

            for message in context.messages:
                turn = observe_model_turn(
                    context,
                    message,
                    scenario,
                    markers=markers,
                    history=history,
                    previous_request=previous,
                    record_evidence=store.record,
                )
                turns.append(turn)
                if turn["provider_calls"] and evidence_class not in paths:
                    paths.append(evidence_class)
                observation["reason"] = observation["reason"] or turn["reason"]
                result = turn["result"]
                if result is None:
                    break
                result = cast(dict[str, object], result)
                request, answer = result.get("request"), result.get("answer")
                if isinstance(request, dict):
                    previous = request
                if _public_text(answer):
                    history.append({"role": "user", "text": message})
                    history.append({"role": "assistant", "text": answer})
                    history = history[-MAX_HISTORY:]
    if evidence.failed:
        observation["reason"] = "evidence_failed"
        observation["status"] = "partial" if turns else "failed"
    else:
        states = {turn["status"] for turn in turns}
        observation["status"] = next(iter(states)) if len(states) == 1 else "partial"
    scanner = CaptureProvider(scenario, markers)
    with _EvidenceErrorBoundary() as export:
        for snapshot in store.snapshots() if store is not None and paths else []:
            try:
                scanner.leakage |= scanner._leaks(snapshot, set())
            except (RecursionError, TypeError, ValueError):
                scanner.capture_incomplete = True
            clean = sanitize_public(snapshot, markers)
            scanner.leakage |= clean != sanitize_public(snapshot, ())
            snapshots.append(cast(dict[str, object], clean))
    if export.failed:
        observation["reason"] = "evidence_failed"
        observation["status"] = (
            "partial" if observation["status"] != "failed" else "failed"
        )
    if scanner.capture_incomplete:
        observation["reason"] = "capture_incomplete"
        observation["status"] = (
            "partial" if observation["status"] != "failed" else "failed"
        )
    if scanner.leakage or any(turn["secret_leak"] is True for turn in turns):
        observation.update(status="failed", reason="secret_leak")
    observation.update(
        injection_applied=scenario.injection_applied,
        injected_text_hash=scenario.injected_text_hash,
    )
    return cast(dict[str, object], sanitize_public(observation, markers))
