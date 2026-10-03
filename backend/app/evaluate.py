from __future__ import annotations

import re
import sys
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agent.provider import LLMProvider


def _print_progress(slot: dict[str, object]) -> None:
    case_id, repeat = slot.get("case_id"), slot.get("repeat")
    condition, status = slot.get("condition"), slot.get("status")
    if (
        type(case_id) is not str
        or re.fullmatch(r"[ABFMPX][0-9]{2}", case_id) is None
        or type(repeat) is not int
        or repeat not in (1, 2, 3)
        or type(condition) is not str
        or condition
        not in (
            "tool_enabled",
            "no_tool",
            "deterministic",
            "controlled_fixture",
            "deterministic_fixture",
        )
        or type(status) is not str
        or status not in ("completed", "failed", "partial", "unassessed")
    ):
        return
    print(f"case_id={case_id} repeat={repeat} condition={condition} status={status}")


def main(
    argv: list[str] | None = None,
    *,
    provider_factory: Callable[[], LLMProvider] | None = None,
) -> int:
    try:
        from app.evaluation_cli_config import load_options
        from app.evaluation_io import EvaluationOutput

        options = load_options(argv, fixture=provider_factory is not None)
        with EvaluationOutput(options.output_dir) as output:
            from app.evaluation_batch import run_evaluation_batch
            from app.evaluation_markdown import render_report
            from app.evaluation_runtime import EvaluationRuntime

            def live_factory() -> LLMProvider:
                from app.providers.bedrock import BedrockConverseProvider

                return BedrockConverseProvider(
                    options.model_id,
                    region=options.region,
                    profile_name=options.profile_name,
                )

            runtime = EvaluationRuntime(
                provider_factory=(
                    provider_factory if provider_factory is not None else live_factory
                ),
                model_id=options.model_id,
                evidence_class=(
                    "deterministic_fake_provider"
                    if provider_factory is not None
                    else "real_bedrock"
                ),
                database_url=options.database_url,
                endpoint=options.endpoint,
            )

            def on_slot(slot: dict[str, object]) -> None:
                output.append_slot(slot)
                _print_progress(slot)

            report = run_evaluation_batch(
                options.corpus,
                runtime,
                region=options.region,
                model_config=options.model_config,
                revision=options.revision,
                on_slot=on_slot,
            )
            markdown = render_report(report, rates=options.rates)
            paths = output.finish(report, markdown)
        for path in paths:
            print(path)
        return 0
    except KeyboardInterrupt:
        print("Evaluation interrupted", file=sys.stderr)
        return 130
    except Exception:  # noqa: BLE001
        print("Evaluation failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
