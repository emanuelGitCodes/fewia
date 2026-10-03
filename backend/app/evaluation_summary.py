from re import fullmatch
from typing import cast

from app.evaluation_summary_metrics import summarize_metrics
from app.evaluation_summary_task import summarize_tasks
from app.evaluation_summary_task_validation import classify_slot

_ERROR = "Invalid evaluation summary input"


def summarize_evaluation(slots: list[dict[str, object]]) -> dict[str, object]:
    if type(slots) is not list:
        raise ValueError(_ERROR)
    grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
    identities: set[tuple[str, str, int]] = set()
    for slot in slots:
        if type(slot) is not dict:
            raise ValueError(_ERROR)
        try:
            facts = classify_slot(slot)
        except ValueError:
            raise ValueError(_ERROR) from None
        if fullmatch(r"[A-Z][0-9]{2}", facts.case_id) is None:
            raise ValueError(_ERROR)
        observation = cast(dict[str, object], slot["observation"])
        for name, expected in (
            ("case_id", facts.case_id),
            ("condition", facts.condition),
        ):
            value = observation.get(name)
            if type(value) is not str or value != expected:
                raise ValueError(_ERROR)
        identity = (facts.condition, facts.case_id, facts.repeat)
        if identity in identities:
            raise ValueError(_ERROR)
        identities.add(identity)
        key = (facts.condition, facts.evidence_class)
        grouped.setdefault(key, []).append(slot)
    groups: list[dict[str, object]] = []
    for (condition, evidence_class), records in sorted(grouped.items()):
        try:
            metrics = summarize_metrics(records)
            tasks = summarize_tasks(records)
        except ValueError:
            raise ValueError(_ERROR) from None
        groups.append(
            {
                "condition": condition,
                "evidence_class": evidence_class,
                "slot_count": len(records),
                "metrics": metrics,
                "tasks": tasks,
            }
        )
    return {"total_slots": len(slots), "groups": groups}
