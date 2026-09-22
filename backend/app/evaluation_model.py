import hashlib
import time
from datetime import date
from typing import Literal, cast

from app.agent import chat_loop
from app.agent.chat_context import MAX_HISTORY, MAX_MESSAGE_LEN
from app.agent.chat_messages import ChatProtocolError
from app.agent.provider import LLMProvider
from app.domain.budget import BudgetResult
from app.domain.catalog import CATALOG_VERSION
from app.evaluation_budget_inputs import fixture_budget

SUPPORTED_IDS = frozenset({"F01", "F02", "F04", "F05", "X02", "X03", "X04", "A01"})
_EVIDENCE = frozenset({"deterministic_fake_provider", "real_bedrock"})


def observe_model_case(
    case: dict[str, object],
    provider: LLMProvider,
    *,
    evidence_class: Literal["deterministic_fake_provider", "real_bedrock"],
    model_id: str,
) -> dict[str, object]:
    """Run chat_loop.run_chat for each user message."""

    def hexdigest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def public(value: object) -> bool:
        return (
            isinstance(value, str)
            and bool(value.strip())
            and len(value) <= MAX_MESSAGE_LEN
        )

    def texts(value: object) -> list[str] | None:
        if type(value) is not list or not value:
            return None
        out: list[str] = []
        for item in value:
            content = None if not isinstance(item, dict) else item.get("content")
            if not isinstance(item, dict) or item.get("role") != "user":
                return None
            if not public(content):
                return None
            out.append(cast(str, content))
        return out

    def setup(inputs: dict[str, object]) -> tuple[date, BudgetResult] | None:
        raw = inputs.get("budget_period")
        if type(raw) is not str:
            return None
        try:
            period = date.fromisoformat(raw)
        except ValueError:
            return None
        if period.day != 1:
            return None
        try:
            return period, fixture_budget(inputs)
        except Exception:
            return None

    def report(
        case_id: str,
        status: str,
        reason: str | None,
        turns: list[dict[str, object]],
        labeled: bool = True,
    ) -> dict[str, object]:
        body: dict[str, object] = {
            "case_id": case_id,
            "status": status,
            "reason": reason,
            "turns": turns,
            "catalog_version": CATALOG_VERSION,
            "prompt_hash": hexdigest(chat_loop.SYSTEM_PROMPT),
            "metrics_status": "unassessed",
        }
        if labeled:
            body["evidence_class"] = evidence_class
            body["model_id"] = model_id
        return body

    bad = "invalid_input"
    if not (
        type(evidence_class) is str
        and evidence_class in _EVIDENCE
        and type(model_id) is str
        and model_id != ""
        and model_id.strip() == model_id
    ):
        return report("invalid_case", bad, bad, [], labeled=False)
    case_id = case.get("id") if isinstance(case, dict) else None
    if type(case_id) is not str or case_id == "":
        return report("invalid_case", bad, bad, [])
    user_texts = texts(case.get("messages"))
    if user_texts is None:
        return report(case_id, bad, bad, [])
    if case_id not in SUPPORTED_IDS:
        return report(case_id, "unassessed", "unsupported_scenario", [])
    raw = case.get("inputs")
    prepared = setup(cast(dict[str, object], raw)) if isinstance(raw, dict) else None
    if prepared is None:
        return report(case_id, bad, bad, [])
    period, budget = prepared
    history: list[dict[str, str]] = []
    previous: dict[str, object] | None = None
    turns: list[dict[str, object]] = []
    failure: str | None = None
    for text in user_texts:
        started = time.monotonic()
        result: dict[str, object] | None
        try:
            result = chat_loop.run_chat(
                provider,
                text,
                budget,
                period,
                previous_request=previous,
                history=history or None,
            )
        except chat_loop.ChatUnavailable:
            failure, result = "provider_unavailable", None
        except ChatProtocolError:
            failure, result = "protocol_error", None
        except Exception:
            failure, result = "unexpected_error", None
        elapsed = time.monotonic() - started
        if result is None:
            turns.append(
                {"status": "failed", "reason": failure, "elapsed_seconds": elapsed}
            )
            break
        turns.append(
            {"status": "completed", "elapsed_seconds": elapsed, "result": result}
        )
        answer = result.get("answer")
        if public(answer):
            history.append({"role": "user", "text": text})
            history.append({"role": "assistant", "text": cast(str, answer)})
            history = history[-MAX_HISTORY:]
        request = result.get("request")
        if isinstance(request, dict):
            previous = request
    done = any(item.get("status") == "completed" for item in turns)
    status = "completed" if failure is None else "partial" if done else "failed"
    return report(case_id, status, failure, turns)
