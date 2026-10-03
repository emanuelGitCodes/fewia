from app.evaluation_summary_task_validation import TaskFacts, classify_slot

_EXECUTION = ("completed", "failed", "partial", "unassessed")
_QUALITY = ("passed", "failed", "unassessed", "not_applicable")
_ERROR = "Invalid evaluation summary input"


def summarize_tasks(slots: list[dict[str, object]]) -> dict[str, object]:
    facts: list[TaskFacts] = []
    group: tuple[str, str] | None = None
    identities: set[tuple[str, str, int]] = set()
    for slot in slots:
        try:
            fact = classify_slot(slot)
        except ValueError:
            raise ValueError(_ERROR) from None
        current = (fact.condition, fact.evidence_class)
        identity = (fact.condition, fact.case_id, fact.repeat)
        if (group is not None and group != current) or identity in identities:
            raise ValueError(_ERROR)
        group = current
        identities.add(identity)
        facts.append(fact)
    slot_counts = dict.fromkeys(_EXECUTION, 0)
    observation_counts = dict.fromkeys(_EXECUTION, 0)
    quality_counts = dict.fromkeys(_QUALITY, 0)
    for fact in facts:
        slot_counts[fact.execution_status] += 1
        observation_counts[fact.observation_status] += 1
        quality_counts[fact.quality_status] += 1
    applicable = len(facts) - quality_counts["not_applicable"]
    passed = quality_counts["passed"]
    assessed = passed + quality_counts["failed"]
    return {
        "condition": group[0] if group else None,
        "evidence_class": group[1] if group else None,
        "execution": {"slot": slot_counts, "observation": observation_counts},
        "quality": {
            "scope": facts[0].quality_scope if facts else None,
            **quality_counts,
            "all_applicable": applicable,
            "assessed_denominator": assessed,
            "conservative_rate": passed / applicable if applicable else None,
            "assessed_only_rate": passed / assessed if assessed else None,
            "coverage": assessed / applicable if applicable else None,
        },
    }
