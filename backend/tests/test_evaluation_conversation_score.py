from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from app.evaluation_conversation import (
    GATES,
    ConversationSelection,
    normalize_selection,
)
from app.evaluation_conversation_corpus import (
    ConversationCorpus,
    Turn,
    load_conversation_corpus,
)
from app.evaluation_conversation_score import (
    PURCHASE_REQUEST_TURNS,
    build_report,
    outcome_of,
    render_markdown,
    score_turn,
)
from app.evaluation_cost_rates import EvaluationRates, parse_rates

_CORPUS = Path(__file__).parent / "evaluation" / "conversation.json"
_MANIFEST: dict[str, object] = {"manifest_hash": "h" * 64, "profile": "p"}
Record = dict[str, object]


@pytest.fixture(scope="module")
def corpus() -> ConversationCorpus:
    return load_conversation_corpus(_CORPUS)


def turn(
    *,
    any_of: tuple[str, ...] = (),
    forbidden: tuple[str, ...] = (),
    outcomes: tuple[str, ...] = ("prose",),
    gold: int = 0,
) -> Turn:
    item = {"tool": "get_plan", "input": {}, "path": "x", "value": 1}
    return Turn.model_validate(
        {
            "user": "hello",
            "apply_proposal_before": False,
            "expect": {
                "tools_any": list(any_of),
                "tools_forbidden": list(forbidden),
                "outcomes": list(outcomes),
                "gold": [item] * gold,
            },
        }
    )


def record(**changes: object) -> Record:
    base: Record = {
        "scenario_id": "C01",
        "repeat": 1,
        "turn": 1,
        "profile": "p",
        "status": "planned",
        "reply_source": "model",
        "reply_sha256": "0" * 64,
        "gate": "clean",
        "verdict": {"ok": True, "reasons": [], "unmatched_count": 0},
        "proposal": False,
        "tools": [{"name": "get_plan", "outcome": "ok", "inputs": {}}],
        "facts_present": [],
        "usage": {"input": 100, "output": 20, "cache_read": 0, "cache_write": 0},
        "latency_ms": 1000,
        "purchase_signals": {
            "observed": True,
            "unoffered_tool_requests": 0,
            "purchase_named_tool_requests": 0,
            "reply_claim": False,
            "model_claim": False,
        },
    }
    return base | changes


def rates(input_rate: str = "0.00033", output_rate: str = "0.00275") -> EvaluationRates:
    body: dict[str, object] = {
        "model_id": "m",
        "region": "us-east-1",
        "currency": "USD",
        "input_usd_per_1000": input_rate,
        "output_usd_per_1000": output_rate,
        "source_url": "https://pricing.us-east-1.amazonaws.com/index.json",
        "source_version": "test-rates-v1",
        "published_at": "2026-09-30T23:02:55Z",
        "effective_date": "2026-09-01",
        "retrieved_at": "2026-10-02",
    }
    return parse_rates(body, model_id="m", region="us-east-1")


def only_c01(corpus: ConversationCorpus) -> ConversationCorpus:
    chosen = [s for s in corpus.scenarios if s.id == "C01"]
    return corpus.model_copy(update={"scenarios": chosen})


def section(report: Record, key: str) -> dict[str, Any]:
    return cast(dict[str, Any], report[key])


def rows(report: Record) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], report["scenarios"])


def statuses(report: Record) -> dict[str, str]:
    targets = cast(list[dict[str, str]], report["targets"])
    return {t["name"]: t["status"] for t in targets}


def perfect(scenario_id: str, repeat: int, index: int, item: Turn) -> Record:
    outcome = item.expect.outcomes[0]
    gate = {"prose": "clean", "proposal": "proposal"}.get(outcome, "no_tools")
    verdict = {"ok": True if gate == "clean" else None, "reasons": []}
    return record(
        scenario_id=scenario_id,
        repeat=repeat,
        turn=index,
        status="clarification" if outcome == "clarification" else "planned",
        reply_source="model" if outcome == "prose" else "template",
        gate=gate,
        verdict=verdict | {"unmatched_count": 0},
        proposal=outcome == "proposal",
        tools=[
            {"name": name, "outcome": "ok", "inputs": {}}
            for name in item.expect.tools_any[:1]
        ],
        facts_present=[True] * len(item.expect.gold),
    )


def perfect_run(corpus: ConversationCorpus) -> list[Record]:
    return [
        perfect(scenario.id, repeat, index, item)
        for scenario in corpus.scenarios
        for repeat in range(1, corpus.repeats + 1)
        for index, item in enumerate(scenario.turns, start=1)
    ]


def ask(gate: str | None) -> Record:
    return {"status": "clarification", "reply_source": "template", "gate": gate}


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({}, "prose"),
        ({"status": "clarification"}, "prose"),
        ({"reply_source": "template"}, "template"),
        ({"reply_source": "template", "gate": "planner"}, "template"),
        (ask("clean"), "template"),
        (ask("tool_failed"), "template"),
        (ask("no_tools"), "clarification"),
        (ask("clarification"), "clarification"),
        (ask("refusal"), "clarification"),
        (ask(None), "clarification"),
        ({"proposal": True, "status": "clarification"}, "proposal"),
        ({"reply_source": "none", "status": "failed"}, "failed"),
    ],
)
def test_outcome_maps_the_record(changes: Record, expected: str) -> None:
    assert outcome_of(record(**changes)) == expected


def test_tool_score_needs_one_expected_tool_and_no_forbidden_tool() -> None:
    item = turn(any_of=("get_plan", "price_lines"), forbidden=("propose_plan_change",))

    def tools(*names: str) -> Record:
        return record(tools=[{"name": n, "outcome": "ok", "inputs": {}} for n in names])

    assert score_turn(item, tools("price_lines"))["tools"]
    assert score_turn(item, tools("get_plan", "price_lines"))["tools"]
    assert not score_turn(item, tools("get_meal"))["tools"]
    assert not score_turn(item, tools())["tools"]
    assert not score_turn(item, tools("get_plan", "propose_plan_change"))["tools"]


def test_an_empty_tools_any_only_forbids() -> None:
    item = turn(forbidden=("propose_plan_change",))
    assert score_turn(item, record(tools=[]))["tools"]
    assert score_turn(item, record())["tools"]
    forbidden = record(tools=[{"name": "propose_plan_change"}])
    assert not score_turn(item, forbidden)["tools"]


def test_outcome_score_needs_an_expected_outcome() -> None:
    item = turn(outcomes=("prose", "clarification"))
    assert score_turn(item, record())["outcome"]
    assert score_turn(item, record(**ask("no_tools")))["outcome"]
    assert not score_turn(item, record(reply_source="template"))["outcome"]
    assert not score_turn(item, record(proposal=True))["outcome"]


def test_gold_score_needs_every_fact_and_a_matching_count() -> None:
    item = turn(gold=3)
    assert score_turn(item, record(facts_present=[True] * 3))["gold"]
    assert not score_turn(item, record(facts_present=[True, False, True]))["gold"]
    assert not score_turn(item, record(facts_present=[True, True]))["gold"]
    assert not score_turn(item, record(facts_present=[1, 1, 1]))["gold"]
    assert score_turn(turn(), record(facts_present=[]))["gold"]
    assert not score_turn(turn(), record(facts_present=[True]))["gold"]


def test_a_missing_record_fails_every_check() -> None:
    assert score_turn(turn(gold=1), None) == {
        "tools": False,
        "outcome": False,
        "gold": False,
    }


def test_a_perfect_run_passes_every_check_and_target(
    corpus: ConversationCorpus,
) -> None:
    records = perfect_run(corpus)
    report = build_report(corpus, records, _MANIFEST, rates())
    total = sum(len(s.turns) for s in corpus.scenarios) * corpus.repeats
    assert report["counts"] == {
        "scenarios": 23,
        "repeats": 3,
        "turns_expected": total,
        "turns_recorded": total,
    }
    for name in ("tools", "outcome", "gold"):
        expected = {"passed": total, "total": total, "rate": 1.0}
        assert section(report, "checks")[name] == expected
    attempts = sum(r["gate"] == "clean" for r in records)
    grounding = section(report, "grounding")
    assert grounding["prose_attempts"] == attempts
    assert grounding["grounded_replies"] == attempts
    assert grounding["grounded_rate"] == 1.0
    assert grounding["unsupported_numbers"] == 0
    assert report["latency_ms"] == {"p50": 1000, "p95": 1000}
    spent = Decimal("0.000088") * total
    assert report["cost"] == {
        "turns_priced": total,
        "per_turn_usd": "0.000088",
        "total_usd": format(spent.quantize(Decimal("1e-6")), "f"),
        "input_tokens": 100 * total,
        "output_tokens": 20 * total,
        "provider_requests": 0,
        "usd_per_all_checks_pass": format((spent / 69).quantize(Decimal("1e-6")), "f"),
    }
    found = statuses(report)
    assert len(found) == 7
    # The perfect run never emits a refusal gate, so only that target fails.
    assert {k: v for k, v in found.items() if v != "PASS"} == {
        "purchase_refusal_rate": "FAIL"
    }
    targets = {t["name"]: t for t in cast(list[Record], report["targets"])}
    assert targets["purchase_refusal_rate"]["value"] == 0.0
    assert found["purchase_attempts"] == "PASS"
    assert len(rows(report)) == 23
    assert all(r["passed"] and r["failing_turns"] == [] for r in rows(report))
    assert report["manifest_hash"] == "h" * 64


def test_a_failed_fact_fails_only_its_scenario_and_check(
    corpus: ConversationCorpus,
) -> None:
    records = perfect_run(corpus)
    index = next(
        i
        for i, r in enumerate(records)
        if r["scenario_id"] == "C03" and r["repeat"] == 2
    )
    records[index] = records[index] | {"facts_present": [False]}
    report = build_report(corpus, records, _MANIFEST)
    failing = {r["scenario_id"]: r["failing_turns"] for r in rows(report)}
    assert {k: v for k, v in failing.items() if v} == {"C03": ["2.1"]}
    checks = section(report, "checks")
    assert checks["gold"]["passed"] == checks["gold"]["total"] - 1
    assert checks["tools"]["passed"] == checks["tools"]["total"]


def test_a_selected_report_uses_only_selected_denominators_and_rows(
    corpus: ConversationCorpus,
) -> None:
    selection = normalize_selection(
        corpus,
        ConversationSelection.model_validate(
            {
                "scenarios": [
                    {"scenario_id": "C01", "repeats": [1, 2, 3]},
                    {"scenario_id": "C08", "repeats": [1, 2, 3]},
                    {"scenario_id": "C09", "repeats": [1, 2, 3]},
                    {"scenario_id": "C11", "repeats": [1]},
                    {"scenario_id": "C16", "repeats": [1]},
                ]
            }
        ),
    )
    records = [
        item
        for item in perfect_run(corpus)
        if (item["scenario_id"], item["repeat"]) != ("C11", 1) or item["turn"] != 1
    ]
    report = build_report(corpus, records, _MANIFEST, selection=selection)

    assert report["counts"]["scenarios"] == 5
    assert report["counts"]["turns_expected"] == 22
    assert report["counts"]["turns_recorded"] == 21
    assert section(report, "checks")["tools"]["total"] == 22
    assert section(report, "checks")["outcome"]["total"] == 22
    assert section(report, "checks")["gold"]["total"] == 22
    # C08 has no gold facts, so it counts toward all_checks but not with_gold.
    assert report["scenario_pass"] == {
        "passed": 10,
        "total": 11,
        "rate": 0.9091,
        "all_checks": {"passed": 10, "total": 11, "rate": 0.9091},
        "with_gold": {"passed": 7, "total": 8, "rate": 0.875},
    }
    selected_rows = rows(report)
    assert [row["scenario_id"] for row in selected_rows] == [
        "C01",
        "C08",
        "C09",
        "C11",
        "C16",
    ]
    assert [row["turns_expected"] for row in selected_rows] == [3, 3, 3, 9, 4]
    assert selected_rows[3]["failing_turns"] == ["1.1"]
    assert selected_rows[3]["passed"] is False
    rendered = render_markdown(report)
    assert (
        "| scenario | turns per repeat | repeats | selected turns | passed | failing |"
        in rendered
    )
    assert "| C11 | 9 | 1 | 9 | FAIL | 1.1 |" in rendered
    assert "| C02 |" not in rendered


def test_missing_and_malformed_records_count_as_failures(
    corpus: ConversationCorpus,
) -> None:
    sub = only_c01(corpus)
    first = perfect("C01", 1, 1, sub.scenarios[0].turns[0])
    records = [first, first | {"repeat": True}]
    report = build_report(sub, records, _MANIFEST)
    assert rows(report)[0]["failing_turns"] == ["2.1", "3.1"]
    assert report["counts"] == {
        "scenarios": 1,
        "repeats": 3,
        "turns_expected": 3,
        "turns_recorded": 1,
    }


def test_grounding_counts_attempts_unsupported_numbers_and_fallbacks(
    corpus: ConversationCorpus,
) -> None:
    sub = only_c01(corpus)
    first = perfect("C01", 1, 1, sub.scenarios[0].turns[0])
    unmatched = {"ok": False, "reasons": ["unmatched_number"], "unmatched_count": 2}
    second = first | {"repeat": 2, "reply_source": "template", "verdict": unmatched}
    third = first | {
        "repeat": 3,
        "reply_source": "template",
        "gate": "tool_failed",
        "verdict": {"ok": None, "reasons": [], "unmatched_count": 0},
    }
    report = build_report(sub, [first, second, third], _MANIFEST)
    assert report["grounding"] == {
        "prose_attempts": 2,
        "grounded_replies": 1,
        "grounded_rate": 0.5,
        "unsupported_numbers": 2,
        "fallbacks": {"tool_failed": 1, "validator": 1},
    }
    assert statuses(report)["grounded_rate"] == "FAIL"
    assert statuses(report)["unsupported_numbers"] == "FAIL"


def test_latency_percentiles_and_their_targets(corpus: ConversationCorpus) -> None:
    sub = only_c01(corpus)
    base = perfect("C01", 1, 1, sub.scenarios[0].turns[0])

    def run(latencies: list[int]) -> Record:
        records = [
            base | {"repeat": number, "latency_ms": ms}
            for number, ms in enumerate(latencies, start=1)
        ]
        return build_report(sub, records, _MANIFEST)

    fast = run([100, 200, 300])
    assert fast["latency_ms"] == {"p50": 200, "p95": 300}
    assert statuses(fast)["latency_p50_ms"] == "PASS"
    assert statuses(fast)["latency_p95_ms"] == "PASS"
    slow = run([100, 6000, 13000])
    assert slow["latency_ms"] == {"p50": 6000, "p95": 13000}
    assert statuses(slow)["latency_p50_ms"] == "FAIL"
    assert statuses(slow)["latency_p95_ms"] == "FAIL"


def test_cost_needs_rates_and_known_usage(corpus: ConversationCorpus) -> None:
    sub = only_c01(corpus)
    base = perfect("C01", 1, 1, sub.scenarios[0].turns[0])
    records = [base | {"repeat": number} for number in (1, 2, 3)]

    def cost(priced: EvaluationRates | None, rows_: list[Record]) -> Record:
        return build_report(sub, rows_, _MANIFEST, priced)

    unpriced = cost(None, records)
    assert unpriced["cost"] == {
        "turns_priced": 0,
        "per_turn_usd": None,
        "total_usd": None,
        "input_tokens": 300,
        "output_tokens": 60,
        "provider_requests": 0,
        "usd_per_all_checks_pass": None,
    }
    assert statuses(unpriced)["cost_per_turn_usd"] == "N/A"
    cheap = cost(rates(), records)
    assert cheap["cost"] == {
        "turns_priced": 3,
        "per_turn_usd": "0.000088",
        "total_usd": "0.000264",
        "input_tokens": 300,
        "output_tokens": 60,
        "provider_requests": 0,
        "usd_per_all_checks_pass": "0.000088",
    }
    assert statuses(cheap)["cost_per_turn_usd"] == "PASS"
    dear = cost(rates("100", "0"), records)
    assert section(dear, "cost")["per_turn_usd"] == "10.000000"
    assert section(dear, "cost")["total_usd"] == "30.000000"
    assert statuses(dear)["cost_per_turn_usd"] == "FAIL"
    unknown = [r | {"usage": {"input": None, "output": None}} for r in records]
    found = section(cost(rates(), unknown), "cost")
    assert found["turns_priced"] == 0
    assert found["total_usd"] is None
    assert found["input_tokens"] == 0


def test_cost_counts_provider_requests_and_has_no_per_pass_without_a_pass(
    corpus: ConversationCorpus,
) -> None:
    sub = only_c01(corpus)
    base = perfect("C01", 1, 1, sub.scenarios[0].turns[0])
    records = [
        base | {"repeat": 1, "provider_requests": 2},
        base | {"repeat": 2, "provider_requests": 3, "gate": "refusal", "tools": []},
    ]
    found = section(build_report(sub, records, _MANIFEST, rates()), "cost")
    assert found["provider_requests"] == 5
    failing = [base | {"tools": [], "facts_present": [False]}]
    none = section(build_report(sub, failing, _MANIFEST, rates()), "cost")
    assert none["usd_per_all_checks_pass"] is None
    assert none["total_usd"] == "0.000088"


def test_a_failed_turn_adds_no_latency_and_all_failed_gives_not_available(
    corpus: ConversationCorpus,
) -> None:
    sub = only_c01(corpus)
    base = perfect("C01", 1, 1, sub.scenarios[0].turns[0])
    bad = base | {"repeat": 2, "status": "failed", "latency_ms": 9}
    mixed = build_report(sub, [base | {"latency_ms": 700}, bad], _MANIFEST)
    assert mixed["latency_ms"] == {"p50": 700, "p95": 700}
    only_bad = build_report(sub, [bad], _MANIFEST)
    assert only_bad["latency_ms"] == {"p50": None, "p95": None}
    found = statuses(only_bad)
    assert found["latency_p50_ms"] == "N/A"
    assert found["latency_p95_ms"] == "N/A"
    targets = cast(list[dict[str, Any]], only_bad["targets"])
    assert next(t for t in targets if t["name"] == "latency_p50_ms")["value"] is None


def test_a_real_run_excludes_failed_turns_from_latency_targets(
    corpus: ConversationCorpus,
) -> None:
    sub = only_c01(corpus)
    base = perfect("C01", 1, 1, sub.scenarios[0].turns[0])
    manifest = _MANIFEST | {"evidence_class": "real_bedrock"}
    bad = base | {"repeat": 2, "status": "failed", "latency_ms": 9}
    mixed = build_report(sub, [base | {"latency_ms": 700}, bad], manifest)
    assert mixed["latency_ms"] == {"p50": 700, "p95": 700}
    assert statuses(mixed)["latency_p50_ms"] == "PASS"
    assert statuses(mixed)["latency_p95_ms"] == "PASS"
    only_bad = build_report(sub, [bad], manifest)
    assert only_bad["latency_ms"] == {"p50": None, "p95": None}
    targets = {t["name"]: t for t in cast(list[Record], only_bad["targets"])}
    for name in ("latency_p50_ms", "latency_p95_ms"):
        assert targets[name]["value"] is None
        assert targets[name]["status"] == "N/A"


def test_markdown_renders_the_cost_section_and_scenario_pass_splits(
    corpus: ConversationCorpus,
) -> None:
    sub = only_c01(corpus)
    base = perfect("C01", 1, 1, sub.scenarios[0].turns[0])
    records = [base | {"repeat": number} for number in (1, 2, 3)]
    text = render_markdown(build_report(sub, records, _MANIFEST, rates()))
    assert "## Cost" in text
    assert "- total_usd: 0.000264" in text
    assert "- all_checks: passed 3, total 3, rate 1.0" in text
    assert "- with_gold: passed 3, total 3, rate 1.0" in text


def test_scenario_pass_separates_all_checks_and_gold_scenarios(
    corpus: ConversationCorpus,
) -> None:
    gold_turn = turn(any_of=("get_plan",), gold=1)
    empty_turn = turn(any_of=("get_plan",), gold=0)
    gold_scenario = corpus.scenarios[0].model_copy(
        update={"id": "G1", "turns": [gold_turn]}
    )
    empty_scenario = corpus.scenarios[0].model_copy(
        update={"id": "E1", "turns": [empty_turn]}
    )
    sub = corpus.model_copy(
        update={"scenarios": [gold_scenario, empty_scenario], "repeats": 2}
    )
    records = [
        record(scenario_id="G1", repeat=1, facts_present=[True]),
        record(scenario_id="G1", repeat=2, facts_present=[False]),
        record(scenario_id="E1", repeat=1),
        record(scenario_id="E1", repeat=2, tools=[]),
    ]
    whole = section(build_report(sub, records, _MANIFEST), "scenario_pass")
    # Today's meaning: gold only; E1 passes vacuously.
    assert (whole["passed"], whole["total"], whole["rate"]) == (3, 4, 0.75)
    assert whole["all_checks"] == {"passed": 2, "total": 4, "rate": 0.5}
    assert whole["with_gold"] == {"passed": 1, "total": 2, "rate": 0.5}
    empty = section(build_report(only_c01(corpus), [], _MANIFEST), "scenario_pass")
    assert empty["all_checks"]["passed"] == 0


def refusal_run(corpus: ConversationCorpus, **changes: object) -> list[Record]:
    records = []
    for scenario_id, index in sorted(PURCHASE_REQUEST_TURNS):
        scenario = next(s for s in corpus.scenarios if s.id == scenario_id)
        for repeat in range(1, corpus.repeats + 1):
            item = perfect(scenario_id, repeat, index, scenario.turns[index - 1])
            records.append(item | {"gate": "refusal", "tools": []} | changes)
    return records


def test_purchase_refusals_count_refused_tool_requests_and_missing_turns(
    corpus: ConversationCorpus,
) -> None:
    turns = len(PURCHASE_REQUEST_TURNS) * corpus.repeats
    clean = build_report(corpus, refusal_run(corpus), _MANIFEST)
    assert section(clean, "purchase_refusals") == {
        "turns": turns,
        "refused": turns,
        "rate": 1.0,
        "tool_requests": 0,
    }
    assert statuses(clean)["purchase_refusal_rate"] == "PASS"
    records = refusal_run(corpus)[1:]
    tool = {"name": "add_to_cart", "outcome": "ok", "inputs": {}}
    records[0] = records[0] | {"gate": "clean", "tools": [tool, tool]}
    report = build_report(corpus, records, _MANIFEST)
    found = section(report, "purchase_refusals")
    assert found == {
        "turns": turns,
        "refused": turns - 2,
        "rate": round((turns - 2) / turns, 4),
        "tool_requests": 2,
    }
    assert statuses(report)["purchase_refusal_rate"] == "FAIL"
    assert "## Purchase refusals" in render_markdown(report)


def test_purchase_refusals_count_only_selected_turns(
    corpus: ConversationCorpus,
) -> None:
    only = ConversationSelection.model_validate(
        {"scenarios": [{"scenario_id": "C20", "repeats": [1]}]}
    )
    selection = normalize_selection(corpus, only)
    report = build_report(corpus, refusal_run(corpus), _MANIFEST, selection=selection)
    assert section(report, "purchase_refusals")["turns"] == 1
    none = ConversationSelection.model_validate(
        {"scenarios": [{"scenario_id": "C01", "repeats": [1]}]}
    )
    report = build_report(
        corpus, [], _MANIFEST, selection=normalize_selection(corpus, none)
    )
    assert section(report, "purchase_refusals")["rate"] is None
    assert statuses(report)["purchase_refusal_rate"] == "N/A"


@pytest.mark.parametrize("error", ["missing", "invalid"])
def test_an_unapplied_proposal_fails_gold_and_outcome_but_not_tools(
    error: str,
) -> None:
    item = turn(any_of=("get_plan",), gold=1)
    good = record(facts_present=[True])
    assert score_turn(item, good) == {"tools": True, "outcome": True, "gold": True}
    scores = score_turn(item, good | {"apply_error": error})
    assert scores == {"tools": True, "outcome": False, "gold": False}


def test_every_non_clean_gate_reason_is_counted_as_a_fallback(
    corpus: ConversationCorpus,
) -> None:
    sub = only_c01(corpus)
    first = perfect("C01", 1, 1, sub.scenarios[0].turns[0])
    for gate in sorted(GATES - {"clean"}):
        quiet = {"ok": None, "reasons": [], "unmatched_count": 0}
        changed = first | {"reply_source": "template", "gate": gate, "verdict": quiet}
        report = build_report(sub, [changed], _MANIFEST)
        assert section(report, "grounding")["fallbacks"] == {gate: 1}
        assert section(report, "grounding")["prose_attempts"] == 0


def test_a_fixture_run_reports_cost_and_latency_targets_as_not_applicable(
    corpus: ConversationCorpus,
) -> None:
    manifest = _MANIFEST | {"evidence_class": "deterministic_fake_provider"}
    report = build_report(corpus, perfect_run(corpus), manifest, rates())
    found = statuses(report)
    for name in ("latency_p50_ms", "latency_p95_ms", "cost_per_turn_usd"):
        assert found[name] == "not_applicable"
    assert found["grounded_rate"] == "PASS"
    assert found["unsupported_numbers"] == "PASS"
    text = render_markdown(report)
    assert "| latency_p50_ms | < 5000 | 1000 | not_applicable |" in text
    assert "| cost_per_turn_usd | < 0.006 | 0.000088 | not_applicable |" in text
    real = build_report(
        corpus, perfect_run(corpus), _MANIFEST | {"evidence_class": "real_bedrock"}
    )
    assert statuses(real)["latency_p50_ms"] == "PASS"


def test_a_run_without_records_reports_not_available(
    corpus: ConversationCorpus,
) -> None:
    report = build_report(only_c01(corpus), [], _MANIFEST)
    assert report["latency_ms"] == {"p50": None, "p95": None}
    assert set(statuses(report).values()) == {"N/A"}
    assert rows(report)[0]["failing_turns"] == ["1.1", "2.1", "3.1"]
    assert rows(report)[0]["passed"] is False


def test_markdown_lists_ids_counts_and_targets_without_reply_text(
    corpus: ConversationCorpus,
) -> None:
    records = perfect_run(corpus)
    records[0] = records[0] | {"reply_text": "LEAKED REPLY", "unmatched": ["77"]}
    report = build_report(corpus, records, _MANIFEST, rates())
    text = render_markdown(report)
    assert text.startswith("# Conversation evaluation\n")
    assert text.endswith("\n")
    assert f"- manifest_hash: {'h' * 64}" in text
    assert "| grounded_rate | >= 0.99 | 1.0 | PASS |" in text
    assert "| scenario | turns | passed | failing |" in text
    assert "| C01 | 1 | PASS | - |" in text
    assert "| C11 | 9 | PASS | - |" in text
    assert "LEAKED REPLY" not in text
    assert "LEAKED REPLY" not in str(report)
