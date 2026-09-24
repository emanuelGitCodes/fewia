from typing import cast

from app.evaluation_score_values import as_map

INVALID = "evaluation input is invalid"
UNASSESSED = "unassessed"
FAKE = "deterministic_fake_provider"
REAL = "real_bedrock"
UNKNOWN = "unknown"
QUALITY_NOTE = (
    "Overall metrics stay unassessed. Final-plan checks cover the last "
    "structured plan only. Counts MUST NOT establish earlier-turn quality, "
    "claim support, or provider readiness."
)
_EXEC = frozenset({"scored", "observed", "failed", UNASSESSED})
_FAKE_ONLY = frozenset({FAKE})
_PLAN_EVIDENCE = frozenset({FAKE, REAL})
_GROUP_KEYS = ("assessed", "passed", "failed", "invalid", "outside_scope")


def _counts(*keys: str) -> dict[str, object]:
    return {key: 0 for key in keys}


def _add(counts: dict[str, object], key: str) -> None:
    counts[key] = cast(int, counts[key]) + 1


def _tally(group: dict[str, object], kind: str) -> None:
    _add(group, kind)
    if kind in {"passed", "failed"}:
        _add(group, "assessed")


def _bools(value: object) -> dict[str, bool] | None:
    body = as_map(value)
    if body is None or not body:
        return None
    out: dict[str, bool] = {}
    for key, item in body.items():
        if type(item) is not bool:
            return None
        out[key] = item
    return out


def _outcome(report: object, allowed: frozenset[str]) -> str:
    if report is None:
        return "outside_scope"
    body = as_map(report)
    checks = None if body is None else _bools(body.get("checks"))
    evidence = None if body is None else body.get("evidence_class")
    if (
        body is None
        or checks is None
        or type(evidence) is not str
        or evidence not in allowed
    ):
        return "invalid"
    return "passed" if all(checks.values()) else "failed"


def _plan(report: object) -> str:
    if report is None:
        return "outside_scope"
    body = as_map(report)
    if body is None or body.get("scope") != "structural_plan":
        return "invalid"
    kind = _outcome(body, _PLAN_EVIDENCE)
    passed = body.get("passed")
    status = body.get("status")
    if kind == "invalid" or type(passed) is not bool or type(status) is not str:
        return "invalid"
    if status == UNASSESSED:
        return "outside_scope" if passed is False else "invalid"
    actual = kind == "passed"
    if actual:
        return "passed" if passed is True and status == "passed" else "invalid"
    if passed is False and status == "failed":
        return "failed"
    return "invalid"


def summarize_evaluation(slots: list[dict[str, object]]) -> dict[str, object]:
    """Count execution and check groups. Metrics stay unassessed."""

    if type(slots) is not list:
        raise ValueError(INVALID)
    execution = _counts("scored", "observed", "failed", UNASSESSED, "invalid")
    fixture = _counts(*_GROUP_KEYS)
    controlled = _counts(*_GROUP_KEYS)
    final_plan = _counts(*_GROUP_KEYS)
    observation = _counts(FAKE, REAL, UNKNOWN)
    for item in slots:
        slot = as_map(item)
        if slot is None:
            _add(execution, "invalid")
            _tally(fixture, "invalid")
            _tally(controlled, "invalid")
            _tally(final_plan, "invalid")
            continue
        status = slot.get("status")
        if type(status) is str and status in _EXEC:
            _add(execution, status)
        else:
            _add(execution, "invalid")
        _tally(fixture, _outcome(slot.get("report"), _FAKE_ONLY))
        _tally(controlled, _outcome(slot.get("controlled_report"), _FAKE_ONLY))
        _tally(final_plan, _plan(slot.get("structural_assessment")))
        if "observation" not in slot:
            continue
        observed = as_map(slot.get("observation"))
        label = None if observed is None else observed.get("evidence_class")
        if type(label) is str and label in _PLAN_EVIDENCE:
            _add(observation, label)
        else:
            _add(observation, UNKNOWN)
    return {
        "total_slots": len(slots),
        "execution_counts": execution,
        "fixture_checks": fixture,
        "controlled_checks": controlled,
        "final_plan_checks": final_plan,
        "evidence_breakdown": {"observation": observation},
        "metrics_status": UNASSESSED,
        "quality_note": QUALITY_NOTE,
    }
