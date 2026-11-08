import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, cast

import pytest

from app import compare_conversation as comparison
from app import evaluate_conversation as evaluation
from app.evaluation_manifest import _hash

_ROOT = Path(__file__).resolve().parents[2]
_CORPUS = _ROOT / "backend/tests/evaluation/conversation.json"


@pytest.fixture(scope="module")
def archives(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("paired-archives")
    selection = root / "selection.json"
    selection.write_text(
        json.dumps(
            {
                "scenarios": [
                    {"scenario_id": "C01", "repeats": [1, 2, 3]},
                    {"scenario_id": "C08", "repeats": [1]},
                ]
            }
        ),
        encoding="utf-8",
    )
    for arm, profile, region in (
        ("nova", "nova-2-lite", "us-east-1"),
        ("luna", "gpt-6-luna", "us"),
    ):
        assert (
            evaluation.main(
                [
                    "--corpus",
                    str(_CORPUS),
                    "--output-dir",
                    str(root / arm),
                    "--profile",
                    profile,
                    "--region",
                    region,
                    "--revision",
                    "b" * 40,
                    "--selection-file",
                    str(selection),
                    "--max-chat-turns",
                    "4",
                    "--fixture",
                ]
            )
            == 0
        )
    return root


@pytest.fixture
def pair(archives: Path, tmp_path: Path) -> tuple[Path, Path]:
    for arm in ("nova", "luna"):
        shutil.copytree(archives / arm, tmp_path / arm)
    return tmp_path / "nova", tmp_path / "luna"


def read_report(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((path / "report.json").read_bytes()))


def save_report(path: Path, report: dict[str, Any]) -> None:
    manifest = report["manifest"]
    manifest["manifest_hash"] = _hash(
        {key: value for key, value in manifest.items() if key != "manifest_hash"}
    )
    report["manifest_hash"] = manifest["manifest_hash"]
    data = json.dumps(report, sort_keys=True).encode()
    (path / "report.json").write_bytes(data)
    marker = json.loads((path / "completion.json").read_bytes())
    marker["sha256"]["report.json"] = hashlib.sha256(data).hexdigest()
    (path / "completion.json").write_text(json.dumps(marker), encoding="utf-8")


def argv(pair: tuple[Path, Path], output: Path) -> list[str]:
    return ["--nova", str(pair[0]), "--luna", str(pair[1]), "--output", str(output)]


def test_fixture_cli_requires_explicit_opt_in_and_preserves_sources(
    pair: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    output = tmp_path / "comparison.json"
    before = [(path / "report.json").read_bytes() for path in pair]
    assert comparison.main(argv(pair, output)) == 2
    assert not output.exists()
    assert comparison.main([*argv(pair, output), "--allow-fixture"]) == 0
    result = json.loads(output.read_bytes())
    assert result["winner"] is None
    assert result["paired_all_checks"] == {
        "nova_wins": 0,
        "luna_wins": 0,
        "both_pass": 4,
        "both_fail": 0,
        "total": 4,
        "ties": 4,
    }
    assert result["luna"]["estimated_usd_per_passing_repeat"] is None
    assert result["luna"]["pricing_coverage_complete"] is False
    assert [(path / "report.json").read_bytes() for path in pair] == before
    saved = output.read_bytes()
    assert comparison.main([*argv(pair, output), "--allow-fixture"]) == 2
    assert output.read_bytes() == saved


def test_paired_outcomes_use_matching_repeat_and_keep_variability(
    pair: tuple[Path, Path],
) -> None:
    report = read_report(pair[1])
    report["scenarios"][0].update(passed=False, failing_turns=["2.1"])
    report["scenario_pass"]["all_checks"].update(passed=3, rate=0.75)
    report["checks"]["outcome"].update(passed=3, rate=0.75)
    save_report(pair[1], report)
    result = comparison.compare(*pair, allow_fixture=True)
    assert result["paired_all_checks"] == {
        "nova_wins": 1,
        "luna_wins": 0,
        "both_pass": 3,
        "both_fail": 0,
        "total": 4,
        "ties": 3,
    }
    summary = result["luna"]
    assert isinstance(summary, dict)
    assert summary["scenario_variability"][0] == {
        "scenario_id": "C01",
        "passed_repeats": 2,
        "total_repeats": 3,
        "mixed_outcomes": True,
        "failing_turns": ["2.1"],
    }


@pytest.mark.parametrize("arm", [0, 1])
def test_status_tampering_with_unchanged_slot_ids_fails_closed(
    pair: tuple[Path, Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    arm: int,
) -> None:
    path = pair[arm] / "slots.jsonl"
    lines = path.read_bytes().splitlines(keepends=True)
    original = json.loads(lines[0])
    record = dict(original)
    record["status"] = "failed" if original["status"] != "failed" else "completed"
    assert record["status"] != original["status"]
    lines[0] = json.dumps(record).encode("utf-8") + b"\n"
    path.write_bytes(b"".join(lines))
    records = [json.loads(line) for line in lines]
    assert len(records) == 4
    assert [(row["scenario_id"], row["repeat"], row["turn"]) for row in records] == [
        ("C01", 1, 1),
        ("C01", 2, 1),
        ("C01", 3, 1),
        ("C08", 1, 1),
    ]
    output = tmp_path / "comparison.json"
    assert comparison.main([*argv(pair, output), "--allow-fixture"]) == 2
    assert not output.exists()
    assert capsys.readouterr().err.strip() == comparison._INVALID


@pytest.mark.parametrize("arm", [0, 1])
def test_missing_journal_hash_fails_closed(
    pair: tuple[Path, Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    arm: int,
) -> None:
    path = pair[arm] / "completion.json"
    marker = json.loads(path.read_bytes())
    del marker["sha256"]["slots.jsonl"]
    path.write_text(json.dumps(marker), encoding="utf-8")
    output = tmp_path / "comparison.json"
    assert comparison.main([*argv(pair, output), "--allow-fixture"]) == 2
    assert not output.exists()
    assert capsys.readouterr().err.strip() == comparison._INVALID


def test_comparison_parses_the_journal_bytes_it_hashes(
    pair: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    reads: list[Path] = []
    read_bytes = Path.read_bytes

    def checked_bytes(path: Path) -> bytes:
        data = read_bytes(path)
        if path.name == "slots.jsonl":
            reads.append(path)
            assert reads.count(path) == 1
            path.write_bytes(b"{}\n")
        return data

    monkeypatch.setattr(Path, "read_bytes", checked_bytes)
    comparison.compare(*pair, allow_fixture=True)
    assert reads == [path / "slots.jsonl" for path in pair]


@pytest.mark.parametrize(
    "key,value",
    [
        ("revision", "c" * 40),
        ("corpus_sha256", "c" * 64),
        ("catalog_hash", "c" * 64),
        ("system_prompt_hash", "c" * 64),
        ("proposal_prompt_hash", "c" * 64),
        ("tool_specs_hash", "c" * 64),
        ("model_id", "unrelated-model"),
        ("evidence_class", "deployed_aws"),
        ("model_config", {"reasoning_effort": "low"}),
        ("region", "us-east-1"),
        ("suite_version", "conversation-eval-v1.5"),
    ],
)
def test_mismatched_or_invalid_manifests_fail_closed(
    pair: tuple[Path, Path],
    tmp_path: Path,
    key: str,
    value: object,
) -> None:
    report = read_report(pair[1])
    report["manifest"][key] = value
    save_report(pair[1], report)
    output = tmp_path / "comparison.json"
    assert comparison.main([*argv(pair, output), "--allow-fixture"]) == 2
    assert not output.exists()


@pytest.mark.parametrize(
    "defect",
    [
        "missing_marker",
        "bad_report_hash",
        "bad_markdown_hash",
        "bad_manifest_hash",
        "slot_count",
        "short_journal",
        "duplicate_slot",
        "partial",
        "missing_signal",
        "duplicate_failure",
        "wrong_repeat",
        "wrong_summary",
        "missing_tool_hash",
        "selection_hash",
        "missing_row",
        "nan_cost",
        "missing_grounding",
        "false_coverage",
        "bad_cache_total",
        "unterminated_journal",
    ],
)
def test_partial_and_malformed_archives_fail_closed(
    pair: tuple[Path, Path],
    tmp_path: Path,
    defect: str,
) -> None:
    path = pair[1]
    report = read_report(path)
    if defect == "missing_marker":
        (path / "completion.json").unlink()
    elif defect == "bad_report_hash":
        (path / "report.json").write_text("{}", encoding="utf-8")
    elif defect == "bad_markdown_hash":
        (path / "report.md").write_text("changed", encoding="utf-8")
    elif defect == "bad_manifest_hash":
        report["manifest"]["revision"] = "d" * 40
        data = json.dumps(report).encode()
        (path / "report.json").write_bytes(data)
        marker = json.loads((path / "completion.json").read_bytes())
        marker["sha256"]["report.json"] = hashlib.sha256(data).hexdigest()
        (path / "completion.json").write_text(json.dumps(marker), encoding="utf-8")
    elif defect == "slot_count":
        marker = json.loads((path / "completion.json").read_bytes())
        marker["slot_count"] = 3
        (path / "completion.json").write_text(json.dumps(marker), encoding="utf-8")
    elif defect in ("short_journal", "duplicate_slot", "unterminated_journal"):
        journal = (path / "slots.jsonl").read_text(encoding="utf-8").splitlines()
        if defect == "short_journal":
            journal = journal[:-1]
        elif defect == "duplicate_slot":
            journal += journal[:1]
        ending = "" if defect == "unterminated_journal" else "\n"
        (path / "slots.jsonl").write_text("\n".join(journal) + ending, encoding="utf-8")
        marker = json.loads((path / "completion.json").read_bytes())
        marker["sha256"]["slots.jsonl"] = hashlib.sha256(
            (path / "slots.jsonl").read_bytes()
        ).hexdigest()
        (path / "completion.json").write_text(json.dumps(marker), encoding="utf-8")
    else:
        if defect == "partial":
            report["counts"]["turns_recorded"] = 3
        elif defect == "missing_signal":
            report["purchase_attempts"]["turns_unobserved"] = 1
        elif defect == "duplicate_failure":
            report["scenarios"][0].update(passed=False, failing_turns=["1.1", "1.1"])
        elif defect == "wrong_repeat":
            report["scenarios"][1].update(passed=False, failing_turns=["2.1"])
        elif defect == "wrong_summary":
            report["scenario_pass"]["all_checks"].update(passed=3, rate=0.75)
        elif defect == "missing_tool_hash":
            del report["manifest"]["tool_specs_hash"]
        elif defect == "selection_hash":
            report["manifest"]["selection"]["scenarios"][0]["repeats"] = [1]
        elif defect == "missing_row":
            report["scenarios"].pop()
        elif defect == "nan_cost":
            report["cost"]["total_usd"] = "NaN"
        elif defect == "missing_grounding":
            del report["grounding"]
        elif defect == "false_coverage":
            report["cost"]["coverage_complete"] = True
        elif defect == "bad_cache_total":
            report["cost"]["cache_read_tokens"] = report["cost"]["input_tokens"] + 1
        save_report(path, report)
    output = tmp_path / "comparison.json"
    assert comparison.main([*argv(pair, output), "--allow-fixture"]) == 2
    assert not output.exists()


def test_fixture_and_real_evidence_cannot_be_pooled(pair: tuple[Path, Path]) -> None:
    report = read_report(pair[0])
    report["manifest"]["evidence_class"] = "real_bedrock"
    save_report(pair[0], report)
    with pytest.raises(ValueError):
        comparison.compare(*pair, allow_fixture=True)


def test_price_alone_selects_no_winner(pair: tuple[Path, Path]) -> None:
    for arm, spent in zip(pair, ("1.000000", "0.100000"), strict=True):
        report = read_report(arm)
        report["cost"].update(
            turns_priced=4,
            total_usd=spent,
            per_turn_usd=str(float(spent) / 4),
        )
        if arm == pair[1]:
            report["cost"].update(coverage_complete=True, turns_unpriced=0)
        save_report(arm, report)
    result = comparison.compare(*pair, allow_fixture=True)
    assert result["winner"] is None
    assert result["luna"]["estimated_usd_per_passing_repeat"] == "0.025000"
