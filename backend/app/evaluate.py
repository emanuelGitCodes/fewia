import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn, cast

from app.agent.chat_loop import SYSTEM_PROMPT
from app.agent.provider import LLMProvider
from app.domain.catalog import CATALOG_VERSION
from app.evaluation_batch import INVALID, _digest, _snapshot, run_observed_evaluation
from app.evaluation_io import (
    FILE_UNAVAILABLE,
    OUTPUT_EXISTS,
    load_corpus,
    open_journal,
    write_record,
    write_result,
)
from app.evaluation_runner import run_evaluation
from app.provider_runtime import build_bedrock
from app.provider_settings import (
    GroceryProviderSettings,
    ProviderConfigurationError,
    load_provider_settings,
)

DEFAULT_CORPUS = Path(__file__).resolve().parents[1] / "tests/evaluation/scenarios.json"
_ARG = "evaluation arguments are invalid"
_FAIL = "evaluation failed"
_CONFIG = "Provider configuration is invalid"


def _err(code: int, text: str) -> int:
    print(text, file=sys.stderr)
    return code


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise SystemExit(_err(2, _ARG))


def _caught(exc: BaseException) -> int:
    if isinstance(exc, ProviderConfigurationError):
        return _err(1, _CONFIG)
    if isinstance(exc, ValueError):
        return _err(1, INVALID)
    if isinstance(exc, OSError):
        return _err(1, OUTPUT_EXISTS if str(exc) == OUTPUT_EXISTS else FILE_UNAVAILABLE)
    return _err(1, _FAIL)


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(prog="app.evaluate")
    parser.add_argument("--mode", choices=("fixture", "bedrock"), default="fixture")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    try:
        args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit as exc:
        return 0 if exc.code in {0, None} else 2
    revision = args.revision
    if (
        type(revision) is not str
        or len(revision) != 40
        or any(ch not in "0123456789abcdef" for ch in revision)
    ):
        return _err(2, _ARG)
    output: Path = args.output
    mode: str = args.mode
    model_id: str | None = None
    settings: GroceryProviderSettings | None = None
    try:
        working = load_corpus(args.corpus)
        corpus_hash, working = _snapshot(working)
        if mode == "bedrock":
            settings = load_provider_settings()
            model_id = settings.bedrock_model_id
            if type(model_id) is not str or model_id.strip() == "":
                raise ProviderConfigurationError()
        manifest: dict[str, object] = {
            "mode": "mixed_fixture_model" if mode == "bedrock" else mode,
            "requested_mode": mode,
            "revision": revision,
            "corpus_hash": corpus_hash,
            "model_id": model_id,
            "catalog_version": CATALOG_VERSION,
            "prompt_hash": _digest(SYSTEM_PROMPT),
            "started_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        journal = open_journal(output, manifest)
    except (KeyboardInterrupt, Exception) as exc:
        return _caught(exc)
    try:
        with journal:
            if mode == "fixture":
                result = run_evaluation(working)
                for slot in cast(list[dict[str, object]], result["slots"]):
                    write_record(journal, slot)
            else:
                if settings is None or type(model_id) is not str:
                    raise ProviderConfigurationError()
                loaded = settings

                def make() -> LLMProvider:
                    provider = build_bedrock(loaded)
                    if provider is None:
                        raise ProviderConfigurationError()
                    return provider

                def on_slot(slot: dict[str, object]) -> None:
                    write_record(journal, slot)

                result = run_observed_evaluation(
                    working,
                    make,
                    model_id=model_id,
                    evidence_class="real_bedrock",
                    on_slot=on_slot,
                )
            result.update(manifest)
            result["metrics_status"] = "unassessed"
            write_result(output, result)
        tallies = {"scored": 0, "observed": 0, "unassessed": 0, "failed": 0}
        rows = result.get("slots")
        if isinstance(rows, list):
            for item in rows:
                status = item.get("status") if isinstance(item, dict) else None
                if type(status) is str and status in tallies:
                    tallies[status] += 1
        summary = {
            "counts": tallies,
            "output": str(output),
            "metrics_status": result.get("metrics_status"),
        }
        print(json.dumps(summary, allow_nan=False))
        return 0
    except (KeyboardInterrupt, Exception) as exc:
        return _caught(exc)


if __name__ == "__main__":
    raise SystemExit(main())
