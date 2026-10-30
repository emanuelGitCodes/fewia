"""Score conversation-eval-v1 observation records and render the report.

Scoring reads hashes, counts, tool names, and fact flags only; no reply text.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from math import ceil

from app.evaluation_conversation_corpus import ConversationCorpus, Turn
from app.evaluation_cost_rates import EvaluationRates

CHECKS = ("tools", "outcome", "gold")
GROUNDED_TARGET = 0.99
P50_TARGET_MS, P95_TARGET_MS = 5000, 12000
COST_TARGET = Decimal("0.006")


def outcome_of(record: dict[str, object]) -> str:
    if record.get("reply_source") == "none":
        return "failed"
    if record.get("proposal") is True:
        return "proposal"
    if record.get("status") == "clarification":
        return "clarification"
    return "prose" if record.get("reply_source") == "model" else "template"


def _list(record: dict[str, object], key: str) -> list[object]:
    value = record.get(key)
    return value if isinstance(value, list) else []


def _map(record: dict[str, object], key: str) -> dict[str, object]:
    value = record.get(key)
    return value if isinstance(value, dict) else {}


def score_turn(turn: Turn, record: dict[str, object] | None) -> dict[str, bool]:
    """Score one turn; a missing record fails every check."""
    if record is None:
        return {check: False for check in CHECKS}
    expect = turn.expect
    called = {t.get("name") for t in _list(record, "tools") if isinstance(t, dict)}
    present = _list(record, "facts_present")
    return {
        "tools": (not expect.tools_any or bool(called & set(expect.tools_any)))
        and not called & set(expect.tools_forbidden),
        "outcome": outcome_of(record) in expect.outcomes,
        "gold": len(present) == len(expect.gold) and all(i is True for i in present),
    }


def _percentile(values: list[int], percent: int) -> int | None:
    ordered = sorted(values)
    return ordered[ceil(percent / 100 * len(ordered)) - 1] if ordered else None


def _rate(passed: int, total: int) -> float | None:
    return round(passed / total, 4) if total else None


def _status(ok: bool | None) -> str:
    return "N/A" if ok is None else "PASS" if ok else "FAIL"


def _target(name: str, goal: str, value: object, ok: bool) -> dict[str, object]:
    status = _status(None if value is None else ok)
    return {"name": name, "target": goal, "value": value, "status": status}


def _key(record: dict[str, object]) -> tuple[str, int, int] | None:
    scenario, repeat, turn = (record.get(k) for k in ("scenario_id", "repeat", "turn"))
    if isinstance(scenario, str) and type(repeat) is int and type(turn) is int:
        return scenario, repeat, turn
    return None


def _fallback(record: dict[str, object]) -> str | None:
    """Name the reason a turn did not end in validated model prose."""
    gate, source = record.get("gate"), record.get("reply_source")
    if gate == "clean":
        return "validator" if source == "template" else None
    if gate is None:
        return None if source == "model" else "no_gate"
    return str(gate)


@dataclass
class _Totals:
    passes: dict[str, int] = field(default_factory=lambda: dict.fromkeys(CHECKS, 0))
    expected: int = 0
    recorded: int = 0
    attempts: int = 0
    grounded: int = 0
    unsupported: int = 0
    cost_turns: int = 0
    cost: Decimal = Decimal(0)
    fallbacks: dict[str, int] = field(default_factory=dict)
    latencies: list[int] = field(default_factory=list)

    def add(self, record: dict[str, object], rates: EvaluationRates | None) -> None:
        self.recorded += 1
        verdict = _map(record, "verdict")
        if record.get("gate") == "clean":
            self.attempts += 1
            self.grounded += verdict.get("ok") is True
        count = verdict.get("unmatched_count")
        self.unsupported += count if type(count) is int else 0
        reason = _fallback(record)
        if reason is not None:
            self.fallbacks[reason] = self.fallbacks.get(reason, 0) + 1
        latency = record.get("latency_ms")
        if type(latency) is int:
            self.latencies.append(latency)
        usage = _map(record, "usage")
        used, made = usage.get("input"), usage.get("output")
        if rates is not None and type(used) is int and type(made) is int:
            self.cost_turns += 1
            self.cost += (
                used * rates.input_usd_per_1000 + made * rates.output_usd_per_1000
            ) / 1000


def build_report(
    corpus: ConversationCorpus,
    records: list[dict[str, object]],
    manifest: dict[str, object],
    rates: EvaluationRates | None = None,
) -> dict[str, object]:
    keyed = {key: r for r in records if (key := _key(r)) is not None}
    totals = _Totals()
    rows: list[dict[str, object]] = []
    for scenario in corpus.scenarios:
        failing: list[str] = []
        for repeat in range(1, corpus.repeats + 1):
            for index, turn in enumerate(scenario.turns, start=1):
                record = keyed.get((scenario.id, repeat, index))
                scores = score_turn(turn, record)
                totals.expected += 1
                for check in CHECKS:
                    totals.passes[check] += scores[check]
                if not all(scores.values()):
                    failing.append(f"{repeat}.{index}")
                if record is not None:
                    totals.add(record, rates)
        rows.append(
            {
                "scenario_id": scenario.id,
                "title": scenario.title,
                "turns": len(scenario.turns),
                "failing_turns": failing,
                "passed": not failing,
            }
        )
    p50, p95 = _percentile(totals.latencies, 50), _percentile(totals.latencies, 95)
    grounded_rate = _rate(totals.grounded, totals.attempts)
    average = totals.cost / totals.cost_turns if totals.cost_turns else None
    per_turn = (
        None if average is None else format(average.quantize(Decimal("1e-6")), "f")
    )
    targets = [
        _target(
            "grounded_rate",
            ">= 0.99",
            grounded_rate,
            grounded_rate is not None and grounded_rate >= GROUNDED_TARGET,
        ),
        _target("unsupported_numbers", "0", totals.unsupported, not totals.unsupported),
        _target(
            "latency_p50_ms",
            f"< {P50_TARGET_MS}",
            p50,
            p50 is not None and p50 < P50_TARGET_MS,
        ),
        _target(
            "latency_p95_ms",
            f"< {P95_TARGET_MS}",
            p95,
            p95 is not None and p95 < P95_TARGET_MS,
        ),
        _target(
            "cost_per_turn_usd",
            f"< {COST_TARGET}",
            per_turn,
            average is not None and average < COST_TARGET,
        ),
    ]
    return {
        "version": "conversation-report-v1",
        "manifest": manifest,
        "manifest_hash": manifest["manifest_hash"],
        "counts": {
            "scenarios": len(corpus.scenarios),
            "repeats": corpus.repeats,
            "turns_expected": totals.expected,
            "turns_recorded": totals.recorded,
        },
        "checks": {
            check: {
                "passed": totals.passes[check],
                "total": totals.expected,
                "rate": _rate(totals.passes[check], totals.expected),
            }
            for check in CHECKS
        },
        "grounding": {
            "prose_attempts": totals.attempts,
            "grounded_replies": totals.grounded,
            "grounded_rate": grounded_rate,
            "unsupported_numbers": totals.unsupported,
            "fallbacks": dict(sorted(totals.fallbacks.items())),
        },
        "latency_ms": {"p50": p50, "p95": p95},
        "cost": {"turns_priced": totals.cost_turns, "per_turn_usd": per_turn},
        "targets": targets,
        "scenarios": rows,
    }


def render_markdown(report: dict[str, object]) -> str:
    """Render the report as markdown; it holds ids, counts, and hashes only."""
    manifest = _map(report, "manifest")
    lines = ["# Conversation evaluation", ""]
    lines += [f"- {key}: {manifest[key]}" for key in sorted(manifest)]
    lines += ["", "## Counts", ""]
    lines += [f"- {key}: {value}" for key, value in _map(report, "counts").items()]
    lines += ["", "## Checks", "", "| check | passed | total | rate |"]
    lines.append("|---|---|---|---|")
    for name, item in _map(report, "checks").items():
        row = item if isinstance(item, dict) else {}
        lines.append(f"| {name} | {row['passed']} | {row['total']} | {row['rate']} |")
    grounding = _map(report, "grounding")
    lines += ["", "## Grounding", ""]
    lines += [f"- {key}: {value}" for key, value in grounding.items()]
    lines += ["", "## Targets (reported, not enforced)", ""]
    lines += ["| metric | target | value | status |", "|---|---|---|---|"]
    for target in _list(report, "targets"):
        if isinstance(target, dict):
            lines.append(
                f"| {target['name']} | {target['target']} | {target['value']} "
                f"| {target['status']} |"
            )
    lines += ["", "## Scenarios", "", "| scenario | turns | passed | failing |"]
    lines.append("|---|---|---|---|")
    for scenario in _list(report, "scenarios"):
        if isinstance(scenario, dict):
            failing = ", ".join(scenario["failing_turns"]) or "-"
            lines.append(
                f"| {scenario['scenario_id']} | {scenario['turns']} "
                f"| {_status(scenario['passed'])} | {failing} |"
            )
    return "\n".join(lines) + "\n"
