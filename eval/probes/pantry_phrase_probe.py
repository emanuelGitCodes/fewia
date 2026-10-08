from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.evaluation_batch import _check_evidence
from app.evaluation_dispatch import run_slot
from app.evaluation_manifest import build_manifest
from app.evaluation_matrix import EvaluationSlot
from app.evaluation_runtime import EvaluationRuntime
from app.evaluation_summary_task_validation import classify_slot
from app.providers.bedrock import BedrockConverseProvider

VARIANTS = [
    (
        "preserve_pantry",
        "F05",
        "Change that to 4 servings and keep my pantry as is.",
    ),
    ("at_home", "F01", "I have black beans at home."),
    ("contraction", "F01", "I've got black beans."),
    ("need_repurchase", "F02", "I need to buy black beans again."),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert (
        subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        == args.revision
    )
    assert not subprocess.check_output(
        ["git", "status", "--porcelain"], text=True
    ).strip()
    raw = Path("tests/evaluation/scenarios.json").read_bytes()
    corpus = json.loads(raw)
    model = "us.amazon.nova-2-lite-v1:0"
    runtime = EvaluationRuntime(
        provider_factory=lambda: BedrockConverseProvider(
            model, region="us-east-1", profile_name="fewia-bedrock-dev"
        ),
        model_id=model,
        evidence_class="real_bedrock",
    )
    args.output.mkdir(parents=True, exist_ok=False)
    results: list[dict[str, Any]] = []
    started = datetime.now(UTC).isoformat()
    with (args.output / "slots.jsonl").open("x") as journal:
        for name, case_id, message in VARIANTS:
            variant_corpus = deepcopy(corpus)
            case = next(c for c in variant_corpus["scenarios"] if c["id"] == case_id)
            original_gold = deepcopy(case["expected"])
            case["messages"][-1]["content"] = message
            assert case["expected"] == original_gold
            manifest = build_manifest(
                variant_corpus,
                model_id=model,
                region="us-east-1",
                model_config={
                    "max_tokens": 4096,
                    "temperature": 0,
                    "reasoning_effort": "low",
                },
            )
            row = run_slot(
                EvaluationSlot(case_id, 1, "tool_enabled", "model", case), runtime
            )
            _check_evidence(row, manifest, "real_bedrock")
            entry = {
                "variant": name,
                "scope": "ad-hoc equivalent wording; not a canonical benchmark slot",
                "message": message,
                "manifest": manifest,
                "gold_unchanged": True,
                "quality": classify_slot(row).quality_status,
                "slot": row,
            }
            results.append(entry)
            journal.write(json.dumps(entry, sort_keys=True) + "\n")
            journal.flush()
            print(
                f"{name} execution={row['status']} quality={entry['quality']}",
                flush=True,
            )
    report = {
        "scope": "ad-hoc pantry wording probes; not a full or canonical benchmark",
        "revision": args.revision,
        "canonical_corpus_sha256": hashlib.sha256(raw).hexdigest(),
        "started_at": started,
        "finished_at": datetime.now(UTC).isoformat(),
        "results": results,
    }
    (args.output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    assert (
        subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        == args.revision
    )
    assert not subprocess.check_output(
        ["git", "status", "--porcelain"], text=True
    ).strip()


if __name__ == "__main__":
    main()
