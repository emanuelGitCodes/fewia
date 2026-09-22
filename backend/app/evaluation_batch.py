import hashlib
import json
from collections.abc import Callable
from typing import Literal, NoReturn, cast

from app.agent.chat_loop import SYSTEM_PROMPT
from app.agent.provider import LLMProvider
from app.domain.catalog import CATALOG_VERSION
from app.evaluation_model import SUPPORTED_IDS, observe_model_case
from app.evaluation_model_score import SUPPORTED_IDS as PLAN_IDS
from app.evaluation_model_score import score_model_plan
from app.evaluation_runner import run_evaluation

INVALID = "evaluation input is invalid"
CASE_COUNT = 30
REPEAT_COUNT = 3
INIT_FAILED = "provider_initialization_failed"
UNSUPPORTED = "unsupported_scenario"
EVIDENCE = frozenset({"deterministic_fake_provider", "real_bedrock"})
EvidenceClass = Literal["deterministic_fake_provider", "real_bedrock"]


def _invalid() -> NoReturn:
    raise ValueError(INVALID) from None


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _meta_ok(model_id: object, evidence_class: object) -> bool:
    return (
        type(evidence_class) is str
        and evidence_class in EVIDENCE
        and type(model_id) is str
        and model_id != ""
        and model_id.strip() == model_id
    )


def _corpus_ok(corpus: object) -> bool:
    if type(corpus) is not dict:
        return False
    body = cast(dict[str, object], corpus)
    version = body.get("version")
    if type(version) is not str or version.strip() == "":
        return False
    if body.get("catalog_version") != CATALOG_VERSION:
        return False
    if type(body.get("repeats")) is not int or body.get("repeats") != REPEAT_COUNT:
        return False
    rows = body.get("scenarios")
    if type(rows) is not list or len(rows) != CASE_COUNT:
        return False
    seen: set[str] = set()
    for item in rows:
        if not isinstance(item, dict):
            return False
        case_id = item.get("id")
        if type(case_id) is not str or case_id.strip() == "" or case_id in seen:
            return False
        seen.add(case_id)
    return len(seen) == CASE_COUNT


def _snapshot(corpus: dict[str, object]) -> tuple[str, dict[str, object]]:
    payload = ""
    try:
        payload = json.dumps(corpus, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError):
        _invalid()
    loaded: object = json.loads(payload)
    if type(loaded) is not dict:
        _invalid()
    return _digest(payload), cast(dict[str, object], loaded)


def _cases(corpus: dict[str, object]) -> dict[str, dict[str, object]]:
    rows = cast(list[object], corpus["scenarios"])
    out: dict[str, dict[str, object]] = {}
    for item in rows:
        case = cast(dict[str, object], item)
        out[cast(str, case["id"])] = case
    return out


def _init_failed(
    case_id: str, evidence_class: EvidenceClass, model_id: str
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "status": "failed",
        "reason": INIT_FAILED,
        "turns": [],
        "catalog_version": CATALOG_VERSION,
        "prompt_hash": _digest(SYSTEM_PROMPT),
        "metrics_status": "unassessed",
        "evidence_class": evidence_class,
        "model_id": model_id,
    }


def run_observed_evaluation(
    corpus: dict[str, object],
    provider_factory: Callable[[], LLMProvider],
    *,
    model_id: str,
    evidence_class: EvidenceClass,
    on_slot: Callable[[dict[str, object]], None] | None = None,
) -> dict[str, object]:
    """Observe supported unassessed slots with one fresh provider each."""

    if not _meta_ok(model_id, evidence_class) or not _corpus_ok(corpus):
        _invalid()
    corpus_hash, working = _snapshot(corpus)
    result = run_evaluation(working)
    cases = _cases(working)
    slots = cast(list[dict[str, object]], result["slots"])
    for slot in slots:
        if slot["status"] == "unassessed":
            case_id = slot["case_id"]
            if type(case_id) is not str or case_id not in SUPPORTED_IDS:
                slot["reason"] = UNSUPPORTED
            else:
                try:
                    provider = provider_factory()
                except Exception:
                    slot["status"] = "failed"
                    slot["observation"] = _init_failed(
                        case_id, evidence_class, model_id
                    )
                else:
                    observation = observe_model_case(
                        cases[case_id],
                        provider,
                        evidence_class=evidence_class,
                        model_id=model_id,
                    )
                    slot["observation"] = observation
                    completed = observation.get("status") == "completed"
                    slot["status"] = "observed" if completed else "failed"
                observed = slot.get("observation")
                if case_id in PLAN_IDS and isinstance(observed, dict):
                    slot["structural_assessment"] = score_model_plan(
                        cases[case_id], observed
                    )
        if on_slot is not None:
            on_slot(slot)
    result["mode"] = "mixed_fixture_model"
    result["corpus_hash"] = corpus_hash
    result["model_id"] = model_id
    result["prompt_hash"] = _digest(SYSTEM_PROMPT)
    result["catalog_version"] = CATALOG_VERSION
    result["metrics_status"] = "unassessed"
    return result
