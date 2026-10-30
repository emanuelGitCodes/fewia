"""CLI for the conversation-eval-v1 suite: python -m app.evaluate_conversation."""

import argparse
import hashlib
import json
import os
import re
import sys
from copy import deepcopy
from pathlib import Path
from typing import NoReturn

from app.agent.chat_loop import PROSE_PROMPT_SUFFIX
from app.agent.provider import LLMProvider
from app.evaluation_conversation import ProviderFor, run_conversation_suite
from app.evaluation_conversation_corpus import ConversationCorpus, Scenario, Turn
from app.evaluation_conversation_score import build_report, render_markdown
from app.evaluation_io import EvaluationOutput
from app.evaluation_manifest import _hash
from app.evaluation_profiles import ModelProfile, rates_for, resolve_profile

_INVALID = "Invalid evaluation CLI input"
FIXTURE_REPLY = "The tool results are shown above."
_UNVERIFIED = "Warning: the profile model id is not verified against Bedrock."
_TOOL_BATCH = 3


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError(_INVALID) from None


class GoldFollowingProvider:
    """Scripted provider: call each distinct gold tool call, then reply in prose."""

    def __init__(self, turn: Turn) -> None:
        distinct = {
            json.dumps([item.tool, item.input], sort_keys=True): item
            for item in turn.expect.gold
        }
        self._calls = [(item.tool, item.input) for item in distinct.values()]
        self._step = 0

    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        start = self._step * _TOOL_BATCH
        batch = self._calls[start : start + _TOOL_BATCH]
        self._step += 1
        usage = {"inputTokens": 100, "outputTokens": 20}
        if not batch:
            content: list[dict[str, object]] = [{"text": FIXTURE_REPLY}]
            return _response("end_turn", content, usage)
        content = [
            {
                "toolUse": {
                    "toolUseId": f"fixture-{self._step}-{number}",
                    "name": name,
                    "input": deepcopy(tool_input),
                }
            }
            for number, (name, tool_input) in enumerate(batch)
        ]
        return _response("tool_use", content, usage)


def _response(
    stop: str, content: list[dict[str, object]], usage: dict[str, int]
) -> dict[str, object]:
    message = {"role": "assistant", "content": content}
    return {"output": {"message": message}, "stopReason": stop, "usage": usage}


def _gold_provider_for(scenario: Scenario, repeat: int, index: int) -> LLMProvider:
    return GoldFollowingProvider(scenario.turns[index - 1])


def _arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = _Parser(prog="fewia-conversation-evaluation", allow_abbrev=False)
    for name in ("--corpus", "--output-dir", "--profile", "--region", "--revision"):
        parser.add_argument(name, required=True)
    parser.add_argument("--rates")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--live-bedrock", action="store_true")
    mode.add_argument("--fixture", action="store_true")
    return parser.parse_args(argv)


def _live_provider_for(profile: ModelProfile, region: str) -> ProviderFor:
    from app.providers.bedrock import BedrockConverseProvider

    if not profile.id_verified:
        print(_UNVERIFIED, file=sys.stderr)
    live = BedrockConverseProvider(
        profile.model_id, region=region, profile_name=os.environ.get("AWS_PROFILE")
    )

    def provider_for(scenario: Scenario, repeat: int, index: int) -> LLMProvider:
        return live

    return provider_for


def main(
    argv: list[str] | None = None,
    *,
    fixture_provider_for: ProviderFor | None = None,
) -> int:
    try:
        args = _arguments(argv)
        if re.fullmatch(r"[0-9a-f]{40}", args.revision) is None:
            raise ValueError(_INVALID)
        if not args.output_dir or Path(args.output_dir).exists():
            raise ValueError(_INVALID)
        profile = resolve_profile(args.profile, args.region)
        # One read: the bytes that are hashed are the bytes that are parsed.
        corpus_bytes = Path(args.corpus).read_bytes()
        corpus = ConversationCorpus.model_validate_json(corpus_bytes)
        rates = (
            rates_for(profile, Path(args.rates), args.region) if args.rates else None
        )
        evidence = (
            "real_bedrock" if args.live_bedrock else "deterministic_fake_provider"
        )
        manifest: dict[str, object] = {
            "version": "conversation-manifest-v1",
            "corpus_sha256": hashlib.sha256(corpus_bytes).hexdigest(),
            "profile": profile.name,
            "model_id": profile.model_id,
            "region": args.region,
            "model_config": profile.model_config,
            "revision": args.revision,
            "evidence_class": evidence,
            "prose_prompt_sha256": hashlib.sha256(
                PROSE_PROMPT_SUFFIX.encode("utf-8")
            ).hexdigest(),
        }
        manifest["manifest_hash"] = _hash(manifest)
    except (ValueError, OSError):
        print(_INVALID, file=sys.stderr)
        return 2
    try:
        provider_for = fixture_provider_for or _gold_provider_for
        if args.live_bedrock:
            provider_for = _live_provider_for(profile, args.region)
        with EvaluationOutput(Path(args.output_dir)) as output:
            records: list[dict[str, object]] = []
            for record in run_conversation_suite(corpus, profile.name, provider_for):
                output.append_slot(record)
                records.append(record)
            report = build_report(corpus, records, manifest, rates)
            paths = output.finish(report, render_markdown(report))
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
