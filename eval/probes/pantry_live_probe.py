from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.evaluation_batch import _check_evidence
from app.evaluation_dispatch import run_slot
from app.evaluation_manifest import build_manifest
from app.evaluation_matrix import prepare_matrix
from app.evaluation_runtime import EvaluationRuntime
from app.evaluation_summary import summarize_evaluation
from app.evaluation_summary_task_validation import classify_slot
from app.providers.bedrock import BedrockConverseProvider


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", default="F05,F01,F02,F04,A02,A04,X03")
    args = parser.parse_args()
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    assert revision == args.revision
    assert not subprocess.check_output(
        ["git", "status", "--porcelain"], text=True
    ).strip()
    corpus_path = Path("tests/evaluation/scenarios.json")
    raw = corpus_path.read_bytes()
    corpus = json.loads(raw)
    cases = args.cases.split(",")
    selected = {value: position for position, value in enumerate(cases)}
    slots = sorted(
        [
            s
            for s in prepare_matrix(corpus)
            if s.condition == "tool_enabled" and s.case_id in selected
        ],
        key=lambda s: (selected[s.case_id], s.repeat),
    )
    assert len(slots) == 3 * len(selected)
    model = "us.amazon.nova-2-lite-v1:0"
    runtime = EvaluationRuntime(
        provider_factory=lambda: BedrockConverseProvider(
            model, region="us-east-1", profile_name="fewia-bedrock-dev"
        ),
        model_id=model,
        evidence_class="real_bedrock",
    )
    manifest = build_manifest(
        corpus,
        model_id=model,
        region="us-east-1",
        model_config={
            "max_tokens": 4096,
            "temperature": 0,
            "reasoning_effort": "low",
        },
    )
    args.output.mkdir(parents=True, exist_ok=False)
    started = datetime.now(UTC).isoformat()
    records: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    with (args.output / "slots.jsonl").open("x") as journal:
        for slot in slots:
            row = run_slot(slot, runtime)
            _check_evidence(row, manifest, "real_bedrock")
            journal.write(json.dumps(row, sort_keys=True) + "\n")
            journal.flush()
            records.append(row)
            quality = classify_slot(row).quality_status
            counts[f"{slot.case_id}:{quality}"] += 1
            print(
                f"{slot.case_id} repeat={slot.repeat} "
                f"execution={row['status']} quality={quality}",
                flush=True,
            )
    report = {
        "scope": "targeted live probes, not a full benchmark",
        "revision": revision,
        "started_at": started,
        "finished_at": datetime.now(UTC).isoformat(),
        "corpus_sha256": hashlib.sha256(raw).hexdigest(),
        "manifest": manifest,
        "counts": dict(counts),
        "summary": summarize_evaluation(records),
        "slots": records,
    }
    (args.output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    assert (
        subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        == revision
    )
    assert not subprocess.check_output(
        ["git", "status", "--porcelain"], text=True
    ).strip()
    print(
        json.dumps(
            {"counts": dict(counts), "report": str(args.output / "report.json")},
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
