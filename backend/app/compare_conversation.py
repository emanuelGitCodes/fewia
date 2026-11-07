"""Compare completed conversation archives without provider calls."""

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import NoReturn, cast

from app.evaluation_cost_rates import parse_rates
from app.evaluation_io import load_json
from app.evaluation_manifest import _hash
from app.evaluation_profiles import resolve_profile

_INVALID = "Invalid or mismatched conversation archives"
_MATCH = (
    "revision",
    "corpus_sha256",
    "suite_version",
    "catalog_hash",
    "system_prompt_hash",
    "proposal_prompt_hash",
    "tool_specs_hash",
    "selection",
    "selection_hash",
    "selected_turn_count",
)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError(_INVALID)


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or any(type(key) is not str for key in value):
        raise ValueError(_INVALID)
    return cast(dict[str, object], value)


def _items(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(_INVALID)
    return cast(list[object], value)


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(_INVALID)
        result[key] = value
    return result


def _decode(data: bytes | str) -> dict[str, object]:
    return _object(json.loads(data, object_pairs_hook=_pairs))


def _integer(value: object, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(_INVALID)
    return value


def _digest(value: object, length: int = 64) -> str:
    if (
        not isinstance(value, str)
        or re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is None
    ):
        raise ValueError(_INVALID)
    return value


def _money(value: object) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(_INVALID)
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise ValueError(_INVALID) from None
    if not result.is_finite() or result < 0:
        raise ValueError(_INVALID)
    return result


def _ratio(value: object, passed: int, total: int) -> None:
    expected = round(passed / total, 4) if total else None
    if value != expected or isinstance(value, bool):
        raise ValueError(_INVALID)


@dataclass(frozen=True)
class _Arm:
    report: dict[str, object]
    report_sha256: str
    manifest: dict[str, object]
    outcomes: dict[tuple[str, int], bool]
    slots: set[tuple[str, int, int]]
    variability: list[dict[str, object]]


def _load(directory: Path, *, luna: bool, allow_fixture: bool) -> _Arm:
    marker = load_json(directory / "completion.json")
    hashes = _object(marker.get("sha256"))
    report_bytes = (directory / "report.json").read_bytes()
    for filename, data in (
        ("report.json", report_bytes),
        ("report.md", (directory / "report.md").read_bytes()),
    ):
        expected = _digest(hashes.get(filename))
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(_INVALID)
    report = _decode(report_bytes)
    manifest = _object(report.get("manifest"))
    digest = _digest(manifest.get("manifest_hash"))
    if digest != report.get("manifest_hash") or digest != _hash(
        {key: value for key, value in manifest.items() if key != "manifest_hash"}
    ):
        raise ValueError(_INVALID)
    if (
        report.get("version") != "conversation-report-v1"
        or manifest.get("version") != "conversation-manifest-v1"
    ):
        raise ValueError(_INVALID)
    if manifest.get("suite_version") != "conversation-eval-v1.6":
        raise ValueError(_INVALID)
    _digest(manifest.get("revision"), 40)
    for key in (
        "corpus_sha256",
        "catalog_hash",
        "system_prompt_hash",
        "proposal_prompt_hash",
        "tool_specs_hash",
    ):
        _digest(manifest.get(key))
    profile_name, region = manifest.get("profile"), manifest.get("region")
    if not isinstance(profile_name, str) or not isinstance(region, str):
        raise ValueError(_INVALID)
    profile = resolve_profile(profile_name, region)
    if profile.name != ("gpt-6-luna" if luna else "nova-2-lite"):
        raise ValueError(_INVALID)
    if (
        manifest.get("model_id") != profile.model_id
        or manifest.get("model_config") != profile.model_config
    ):
        raise ValueError(_INVALID)
    evidence = manifest.get("evidence_class")
    if evidence != ("real_openai" if luna else "real_bedrock") and not (
        allow_fixture and evidence == "deterministic_fake_provider"
    ):
        raise ValueError(_INVALID)
    if "rates" in manifest:
        parse_rates(manifest["rates"], model_id=profile.model_id, region=region)
    elif evidence == "real_openai":
        raise ValueError(_INVALID)
    counts = _object(report.get("counts"))
    expected_turns = _integer(counts.get("turns_expected"), 1)
    if (
        _integer(counts.get("turns_recorded")) != expected_turns
        or _integer(marker.get("slot_count")) != expected_turns
        or _integer(counts.get("repeats")) != 3
    ):
        raise ValueError(_INVALID)
    selected: dict[str, list[int]] | None = None
    if "selection" in manifest:
        selection = _object(manifest["selection"])
        if (
            _hash(selection) != manifest.get("selection_hash")
            or _integer(manifest.get("selected_turn_count")) != expected_turns
        ):
            raise ValueError(_INVALID)
        selected = {}
        for item in _items(selection.get("scenarios")):
            entry = _object(item)
            scenario = entry.get("scenario_id")
            numbers = [_integer(i, 1) for i in _items(entry.get("repeats"))]
            if not isinstance(scenario, str) or scenario in selected or not numbers:
                raise ValueError(_INVALID)
            if numbers != sorted(set(numbers)) or max(numbers) > 3:
                raise ValueError(_INVALID)
            selected[scenario] = numbers
    elif "selection_hash" in manifest or "selected_turn_count" in manifest:
        raise ValueError(_INVALID)
    outcomes: dict[tuple[str, int], bool] = {}
    slots: set[tuple[str, int, int]] = set()
    variability: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in _items(report.get("scenarios")):
        row = _object(item)
        scenario = row.get("scenario_id")
        if (
            not isinstance(scenario, str)
            or scenario in seen
            or re.fullmatch(r"C(?:0[1-9]|1[0-9]|2[0-5])", scenario) is None
        ):
            raise ValueError(_INVALID)
        seen.add(scenario)
        turns = _integer(row.get("turns"), 1)
        repeats = [1, 2, 3] if selected is None else selected.get(scenario)
        if not repeats:
            raise ValueError(_INVALID)
        if selected is not None:
            row_repeats = [_integer(i, 1) for i in _items(row.get("repeats"))]
            if row_repeats != repeats or _integer(
                row.get("turns_expected")
            ) != turns * len(repeats):
                raise ValueError(_INVALID)
        failures: set[tuple[int, int]] = set()
        for failure in _items(row.get("failing_turns")):
            if (
                not isinstance(failure, str)
                or re.fullmatch(r"[1-3]\.[1-9][0-9]*", failure) is None
            ):
                raise ValueError(_INVALID)
            repeat, turn = (int(part) for part in failure.split("."))
            if repeat not in repeats or turn > turns or (repeat, turn) in failures:
                raise ValueError(_INVALID)
            failures.add((repeat, turn))
        if type(row.get("passed")) is not bool or row["passed"] != (not failures):
            raise ValueError(_INVALID)
        passed = 0
        for repeat in repeats:
            ok = not any(number == repeat for number, _ in failures)
            outcomes[scenario, repeat] = ok
            passed += ok
            slots.update((scenario, repeat, turn) for turn in range(1, turns + 1))
        variability.append(
            {
                "scenario_id": scenario,
                "passed_repeats": passed,
                "total_repeats": len(repeats),
                "mixed_outcomes": 0 < passed < len(repeats),
                "failing_turns": row["failing_turns"],
            }
        )
    expected_ids = (
        set(selected)
        if selected is not None
        else {f"C{number:02}" for number in range(1, 26)}
    )
    if (
        seen != expected_ids
        or _integer(counts.get("scenarios")) != len(seen)
        or len(slots) != expected_turns
    ):
        raise ValueError(_INVALID)
    journal: set[tuple[str, int, int]] = set()
    journal_text = (directory / "slots.jsonl").read_text(encoding="utf-8")
    if not journal_text.endswith("\n"):
        raise ValueError(_INVALID)
    for line in journal_text.splitlines():
        record = _decode(line)
        scenario = record.get("scenario_id")
        if not isinstance(scenario, str):
            raise ValueError(_INVALID)
        slot_key = (
            scenario,
            _integer(record.get("repeat"), 1),
            _integer(record.get("turn"), 1),
        )
        if slot_key not in slots or slot_key in journal:
            raise ValueError(_INVALID)
        journal.add(slot_key)
    if journal != slots:
        raise ValueError(_INVALID)
    success = _object(report.get("scenario_pass"))
    for summary in (
        success,
        _object(success.get("all_checks")),
        _object(success.get("with_gold")),
    ):
        passed_count = _integer(summary.get("passed"))
        total_count = _integer(summary.get("total"))
        if passed_count > total_count or total_count > len(outcomes):
            raise ValueError(_INVALID)
        _ratio(summary.get("rate"), passed_count, total_count)
    all_checks = _object(success["all_checks"])
    if (
        all_checks["total"] != len(outcomes)
        or all_checks["passed"] != sum(outcomes.values())
        or success["total"] != len(outcomes)
    ):
        raise ValueError(_INVALID)
    checks = _object(report.get("checks"))
    for name in ("tools", "outcome", "gold"):
        check = _object(checks.get(name))
        passed_count = _integer(check.get("passed"))
        if (
            _integer(check.get("total")) != expected_turns
            or passed_count > expected_turns
        ):
            raise ValueError(_INVALID)
        _ratio(check.get("rate"), passed_count, expected_turns)
    _validate_summaries(report, expected_turns, luna=luna)
    return _Arm(
        report,
        hashlib.sha256(report_bytes).hexdigest(),
        manifest,
        outcomes,
        slots,
        variability,
    )


def _validate_summaries(report: dict[str, object], turns: int, *, luna: bool) -> None:
    purchase = _object(report.get("purchase_attempts"))
    if (
        _integer(purchase.get("turns_unobserved")) != 0
        or _integer(purchase.get("turns_observed")) != turns
    ):
        raise ValueError(_INVALID)
    for name in (
        "turns_with_attempt",
        "unoffered_tool_requests",
        "purchase_named_tool_requests",
        "reply_claims",
        "model_claims",
    ):
        _integer(purchase.get(name))
    refusals = _object(report.get("purchase_refusals"))
    refused = _integer(refusals.get("refused"))
    requested = _integer(refusals.get("turns"))
    if refused > requested or requested > turns:
        raise ValueError(_INVALID)
    _ratio(refusals.get("rate"), refused, requested)
    _integer(refusals.get("tool_requests"))
    grounding = _object(report.get("grounding"))
    grounded = _integer(grounding.get("grounded_replies"))
    attempts = _integer(grounding.get("prose_attempts"))
    if grounded > attempts or attempts > turns:
        raise ValueError(_INVALID)
    _ratio(grounding.get("grounded_rate"), grounded, attempts)
    _integer(grounding.get("unsupported_numbers"))
    for value in _object(grounding.get("fallbacks")).values():
        _integer(value)
    latency = _object(report.get("latency_ms"))
    for name in ("p50", "p95"):
        if name not in latency:
            raise ValueError(_INVALID)
        if latency.get(name) is not None:
            _integer(latency[name])
    if (latency["p50"] is None) != (latency["p95"] is None):
        raise ValueError(_INVALID)
    if latency["p50"] is not None and _integer(latency["p50"]) > _integer(
        latency["p95"]
    ):
        raise ValueError(_INVALID)
    cost = _object(report.get("cost"))
    priced = _integer(cost.get("turns_priced"))
    if priced > turns:
        raise ValueError(_INVALID)
    for name in ("input_tokens", "output_tokens", "provider_requests"):
        _integer(cost.get(name))
    for name in ("total_usd", "per_turn_usd", "usd_per_all_checks_pass"):
        if name not in cost:
            raise ValueError(_INVALID)
        _money(cost.get(name))
    if (priced > 0) != (cost["total_usd"] is not None) or (priced > 0) != (
        cost["per_turn_usd"] is not None
    ):
        raise ValueError(_INVALID)
    if luna:
        if (
            _integer(cost.get("cache_read_tokens")) > _integer(cost["input_tokens"])
            or _integer(cost.get("cache_unknown_turns")) > turns
            or _integer(cost.get("turns_unpriced")) != turns - priced
            or type(cost.get("coverage_complete")) is not bool
            or cost["coverage_complete"] != (priced == turns)
        ):
            raise ValueError(_INVALID)


def _summary(arm: _Arm) -> dict[str, object]:
    report = arm.report
    cost = _object(report["cost"])
    turns = _object(report["counts"])["turns_expected"]
    passing = sum(arm.outcomes.values())
    complete = cost["turns_priced"] == turns
    total = _money(cost.get("total_usd"))
    per_pass = None
    if complete and passing and total is not None:
        per_pass = format((total / passing).quantize(Decimal("1e-6")), "f")
    return {
        "model_id": arm.manifest["model_id"],
        "evidence_class": arm.manifest["evidence_class"],
        "manifest_hash": arm.manifest["manifest_hash"],
        "report_sha256": arm.report_sha256,
        "scenario_pass": report["scenario_pass"],
        "checks": report["checks"],
        "purchase_refusals": report["purchase_refusals"],
        "purchase_attempts": report["purchase_attempts"],
        "grounding": report["grounding"],
        "latency_ms": report["latency_ms"],
        "cost": cost,
        "pricing_coverage_complete": complete,
        "estimated_usd_per_passing_repeat": per_pass,
        "cost_note": (
            "Full coverage."
            if complete
            else "Partial or absent pricing; per-pass estimate unavailable."
        ),
        "scenario_variability": arm.variability,
    }


def compare(
    nova: Path, luna: Path, *, allow_fixture: bool = False
) -> dict[str, object]:
    first = _load(nova, luna=False, allow_fixture=allow_fixture)
    second = _load(luna, luna=True, allow_fixture=allow_fixture)
    if any(first.manifest.get(key) != second.manifest.get(key) for key in _MATCH):
        raise ValueError(_INVALID)
    if first.slots != second.slots:
        raise ValueError(_INVALID)
    fixtures = [
        arm.manifest["evidence_class"] == "deterministic_fake_provider"
        for arm in (first, second)
    ]
    if fixtures[0] != fixtures[1]:
        raise ValueError(_INVALID)
    paired = dict.fromkeys(("nova_wins", "luna_wins", "both_pass", "both_fail"), 0)
    for key, nova_pass in first.outcomes.items():
        luna_pass = second.outcomes[key]
        name = "both_pass" if nova_pass and luna_pass else "both_fail"
        if nova_pass != luna_pass:
            name = "nova_wins" if nova_pass else "luna_wins"
        paired[name] += 1
    return {
        "version": "conversation-comparison-v1",
        "matched_inputs": {key: first.manifest.get(key) for key in _MATCH},
        "nova": _summary(first),
        "luna": _summary(second),
        "paired_all_checks": paired
        | {
            "total": len(first.outcomes),
            "ties": paired["both_pass"] + paired["both_fail"],
        },
        "winner": None,
        "limits": [
            "Paired outcomes use the same scenario and repeat from failing_turns.",
            "Scenario repeats share prompts. These counts do not establish "
            "statistical significance or causation.",
            "Grounding uses the shared numeric validator, "
            "not a complete factual-claim audit.",
            "Latency and token totals reuse arm summaries. "
            "Failed turns are excluded from latency.",
            "Cost estimates use recorded usage and rates. "
            "They are not invoices. Price alone selects no winner.",
            (
                "Fixture results provide no live model quality, "
                "latency, or cost evidence."
                if fixtures[0]
                else "Real Bedrock and real OpenAI evidence remain separate classes."
            ),
        ],
    }


def main(argv: list[str] | None = None) -> int:
    try:
        parser = _Parser(allow_abbrev=False)
        for name in ("--nova", "--luna", "--output"):
            parser.add_argument(name, required=True)
        parser.add_argument("--allow-fixture", action="store_true")
        args = parser.parse_args(argv)
        result = compare(
            Path(args.nova), Path(args.luna), allow_fixture=args.allow_fixture
        )
        data = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"
        with Path(args.output).open("x", encoding="utf-8") as handle:
            handle.write(data)
    except (ValueError, OSError, TypeError, KeyError, ArithmeticError):
        print(_INVALID, file=sys.stderr)
        return 2
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
