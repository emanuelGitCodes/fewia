import hashlib
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from app import evaluate_conversation as cli
from app import evaluation_io_json
from app.agent import chat_loop
from app.agent.provider import LLMProvider
from app.evaluation_conversation_corpus import Scenario, load_conversation_corpus
from app.evaluation_io import EvaluationOutput
from app.evaluation_manifest import _hash
from app.evaluation_profiles import resolve_profile
from app.providers import bedrock

_CORPUS = Path(__file__).parent / "evaluation" / "conversation.json"
_SELECTION = (
    Path(__file__).resolve().parents[2]
    / "eval"
    / "experiments"
    / "conversation-quality"
    / "selection.json"
)
_REVISION = "b" * 40


def _argv(out: Path, **override: str | None) -> list[str]:
    options: dict[str, str | None] = {
        "--corpus": str(_CORPUS),
        "--output-dir": str(out),
        "--profile": "nova-2-lite",
        "--region": "us-east-1",
        "--revision": _REVISION,
        "--selection-file": None,
        "--max-chat-turns": None,
    }
    options.update(override)
    args: list[str] = []
    for option, value in options.items():
        if value is not None:
            args.extend((option, value))
    return [*args, "--fixture"]


def test_a_fixture_run_writes_the_four_files_and_reports_every_scenario(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    corpus = load_conversation_corpus(_CORPUS)
    out = tmp_path / "out"
    assert cli.main(_argv(out)) == 0
    names = {"slots.jsonl", "report.json", "report.md", "completion.json"}
    assert names <= {path.name for path in out.iterdir()}
    printed = capsys.readouterr().out.splitlines()
    assert {Path(line).name for line in printed} == names - {"slots.jsonl"}

    expected = sum(len(s.turns) for s in corpus.scenarios) * corpus.repeats
    assert expected == 123
    assert sum(len(s.turns) for s in corpus.scenarios) == 41
    slots = (out / "slots.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(slots) == expected
    completion = json.loads((out / "completion.json").read_text(encoding="utf-8"))
    assert completion["slot_count"] == expected
    assert set(completion["sha256"]) == {"report.json", "report.md", "slots.jsonl"}
    for filename, digest in completion["sha256"].items():
        assert digest == hashlib.sha256((out / filename).read_bytes()).hexdigest()

    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    ids = [s.id for s in corpus.scenarios]
    assert len(ids) == 25
    assert [row["scenario_id"] for row in report["scenarios"]] == ids
    assert report["counts"]["turns_recorded"] == expected
    assert report["counts"]["turns_expected"] == 123
    assert all(check["total"] == 123 for check in report["checks"].values())
    found_targets = {t["name"]: t for t in report["targets"]}
    assert found_targets["purchase_attempts"]["value"] == 0
    assert found_targets["purchase_attempts"]["status"] == "PASS"
    assert report["purchase_attempts"]["turns_observed"] == 123
    assert report["purchase_attempts"]["turns_unobserved"] == 0
    assert report["manifest"]["evidence_class"] == "deterministic_fake_provider"
    assert report["manifest"]["profile"] == "nova-2-lite"
    assert report["manifest"]["revision"] == _REVISION
    assert "selection" not in report["manifest"]
    assert "selection_hash" not in report["manifest"]
    assert "selected_turn_count" not in report["manifest"]
    assert set(report["manifest"]) == {
        "version",
        "corpus_sha256",
        "profile",
        "model_id",
        "region",
        "model_config",
        "revision",
        "evidence_class",
        "suite_version",
        "catalog_hash",
        "system_prompt_hash",
        "proposal_prompt_hash",
        "tool_specs_hash",
        "manifest_hash",
    }
    markdown = (out / "report.md").read_text(encoding="utf-8")
    for scenario_id in ids:
        assert f"| {scenario_id} |" in markdown
    assert report["manifest_hash"] in markdown
    for check in ("tools", "outcome", "gold"):
        assert report["checks"][check]["rate"] == 1.0
    assert report["grounding"]["grounded_rate"] == 1.0
    found = {t["name"]: t["status"] for t in report["targets"]}
    for name in ("latency_p50_ms", "latency_p95_ms", "cost_per_turn_usd"):
        assert found[name] == "not_applicable"


def test_output_finish_keeps_the_default_marker_shape(tmp_path: Path) -> None:
    out = tmp_path / "default-output"
    with EvaluationOutput(out) as output:
        output.append_slot({"status": "completed"})
        output.finish({}, "report")
    marker = json.loads((out / "completion.json").read_bytes())
    assert set(marker) == {"sha256", "slot_count"}
    assert set(marker["sha256"]) == {"report.json", "report.md"}
    assert marker["slot_count"] == 1


@pytest.mark.parametrize(
    "flags",
    [
        ["--detailed-export"],
        ["--synthetic-inputs"],
        ["--detailed-export", "--synthetic-inputs"],
    ],
)
def test_detailed_export_rejects_arbitrary_corpus_before_output_or_provider(
    tmp_path: Path, flags: list[str]
) -> None:
    corpus = tmp_path / "conversation.json"
    corpus.write_bytes(_CORPUS.read_bytes() + b" ")
    out = tmp_path / "out"
    calls: list[str] = []

    def provider_for(scenario: Scenario, repeat: int, index: int) -> LLMProvider:
        calls.append(scenario.id)
        pytest.fail("The provider MUST NOT run.")

    assert (
        cli.main(
            [*_argv(out, **{"--corpus": str(corpus)}), *flags],
            fixture_provider_for=provider_for,
        )
        == 2
    )
    assert calls == []
    assert not out.exists()


def test_verified_synthetic_conversation_allows_bounded_detailed_json(
    tmp_path: Path,
) -> None:
    out = tmp_path / "detailed"
    assert cli.main([*_argv(out), "--detailed-export", "--synthetic-inputs"]) == 0
    records = [
        json.loads(line) for line in (out / "slots.jsonl").read_bytes().splitlines()
    ]
    assert len(records) == 123
    assert any(record.get("reply_sha256") for record in records)
    assert all("reasoningContent" not in json.dumps(record) for record in records)


def test_default_conversation_artifacts_remove_nested_private_markers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from collections.abc import Iterator

    from app.evaluation_conversation import ConversationCorpus, ConversationSelection

    marker = "ARBITRARY_CONVERSATION_PRIVATE_MARKER"
    original = cli.run_conversation_suite
    in_memory: list[dict[str, object]] = []

    def injected(
        corpus: ConversationCorpus,
        profile: str,
        provider_for: cli.ProviderFor,
        *,
        selection: ConversationSelection | None = None,
    ) -> Iterator[dict[str, object]]:
        for record in original(corpus, profile, provider_for, selection=selection):
            record["private"] = {"result": marker}
            tools = record.get("tools")
            if isinstance(tools, list):
                for tool in tools:
                    if isinstance(tool, dict):
                        tool["inputs"] = {"raw": marker}
            in_memory.append(record)
            yield record

    monkeypatch.setattr(cli, "run_conversation_suite", injected)
    out = tmp_path / "out"
    assert cli.main(_argv(out)) == 0
    assert in_memory and marker in json.dumps(in_memory)
    for artifact in out.iterdir():
        if artifact.is_file():
            assert marker.encode() not in artifact.read_bytes()
    rows = [
        json.loads(line) for line in (out / "slots.jsonl").read_bytes().splitlines()
    ]
    assert all("inputs" not in json.dumps(row) for row in rows)


def test_a_fixture_run_reports_the_purchase_refusal_rate(tmp_path: Path) -> None:
    out = tmp_path / "refusals"
    assert cli.main(_argv(out)) == 0
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    refusals = report["purchase_refusals"]
    assert refusals["turns"] == 15
    assert refusals["refused"] == 0
    found = {t["name"]: t for t in report["targets"]}
    assert found["purchase_refusal_rate"]["status"] == "not_applicable"
    assert "## Purchase refusals" in (out / "report.md").read_text(encoding="utf-8")


class _RaisingProvider:
    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        raise RuntimeError("provider down")


def test_a_raising_provider_on_unrouted_turns_exits_3_with_every_artifact(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "down"
    selection = tmp_path / "selection.json"
    selection.write_text(
        json.dumps({"scenarios": [{"scenario_id": "C01", "repeats": [1, 2, 3]}]}),
        encoding="utf-8",
    )

    def provider_for(scenario: Scenario, repeat: int, index: int) -> LLMProvider:
        return _RaisingProvider()

    argv = _argv(out, **{"--selection-file": str(selection), "--max-chat-turns": "3"})
    assert cli.main(argv, fixture_provider_for=provider_for) == 3
    captured = capsys.readouterr()
    assert "Evaluation incomplete" in captured.err
    names = {"slots.jsonl", "report.json", "report.md", "completion.json"}
    assert names <= {path.name for path in out.iterdir()}
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["purchase_attempts"]["turns_unobserved"] > 0
    found = {t["name"]: t for t in report["targets"]}
    for name in ("latency_p50_ms", "latency_p95_ms"):
        assert found[name]["value"] is None
        assert found[name]["status"] == "not_applicable"
    assert "provider down" not in (out / "slots.jsonl").read_text(encoding="utf-8")


def test_a_selected_fixture_run_emits_only_the_selected_turns(
    tmp_path: Path,
) -> None:
    out = tmp_path / "selected"
    assert (
        cli.main(
            _argv(
                out,
                **{
                    "--selection-file": str(_SELECTION),
                    "--max-chat-turns": "22",
                },
            )
        )
        == 0
    )
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    records = [
        json.loads(line)
        for line in (out / "slots.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    expected_selection = {
        "scenarios": [
            {"scenario_id": "C01", "repeats": [1, 2, 3]},
            {"scenario_id": "C08", "repeats": [1, 2, 3]},
            {"scenario_id": "C09", "repeats": [1, 2, 3]},
            {"scenario_id": "C11", "repeats": [1]},
            {"scenario_id": "C16", "repeats": [1]},
        ]
    }
    manifest = report["manifest"]
    assert manifest["corpus_sha256"] == hashlib.sha256(_CORPUS.read_bytes()).hexdigest()
    assert manifest["system_prompt_hash"] == _hash(chat_loop.SYSTEM_PROMPT)
    assert manifest["proposal_prompt_hash"] == _hash(chat_loop.PROPOSAL_PROMPT_SUFFIX)
    assert manifest["tool_specs_hash"] == cli.tool_specs_hash()
    assert (
        manifest["model_config"]
        == resolve_profile("nova-2-lite", "us-east-1").model_config
    )
    assert manifest["evidence_class"] == "deterministic_fake_provider"
    assert manifest["selection"] == expected_selection
    assert manifest["selection_hash"] == _hash(expected_selection)
    assert manifest["selected_turn_count"] == 22
    covered = {key: value for key, value in manifest.items() if key != "manifest_hash"}
    assert manifest["manifest_hash"] == _hash(covered)

    pairs = {(row["scenario_id"], row["repeat"]) for row in records}
    assert pairs == {
        (item["scenario_id"], repeat)
        for item in expected_selection["scenarios"]
        for repeat in item["repeats"]
    }
    assert len(records) == 22
    assert report["counts"]["turns_expected"] == 22
    assert report["counts"]["turns_recorded"] == 22
    assert report["scenario_pass"]["total"] == 11
    assert [row["scenario_id"] for row in report["scenarios"]] == [
        "C01",
        "C08",
        "C09",
        "C11",
        "C16",
    ]
    assert [row["turns_expected"] for row in report["scenarios"]] == [3, 3, 3, 9, 4]


def test_the_manifest_hashes_the_bytes_that_were_parsed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus_path = tmp_path / "corpus.json"
    corpus_bytes = _CORPUS.read_bytes()
    corpus_path.write_bytes(corpus_bytes)
    reads: list[Path] = []
    original = evaluation_io_json._read

    def counting(path: Path, max_bytes: int) -> bytes:
        reads.append(path)
        raw = original(path, max_bytes)
        if path == corpus_path:
            path.write_bytes(b"{}")
        return raw

    monkeypatch.setattr(evaluation_io_json, "_read", counting)
    out = tmp_path / "out"
    assert cli.main(_argv(out, **{"--corpus": str(corpus_path)})) == 0
    assert reads.count(corpus_path) == 1
    assert corpus_path.read_bytes() == b"{}"
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(corpus_bytes).hexdigest()
    assert report["manifest"]["corpus_sha256"] == digest


@pytest.mark.parametrize(
    "override",
    [
        {"--profile": "no-such-profile"},
        {"--region": "eu-west-1"},
        {"--revision": "abc123"},
        {"--revision": "A" * 40},
        {"--corpus": "missing-corpus.json"},
        {"--rates": "missing-rates.json"},
    ],
)
def test_bad_arguments_exit_2_and_write_nothing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    override: dict[str, str | None],
) -> None:
    out = tmp_path / "out"
    assert cli.main(_argv(out, **override)) == 2
    assert not out.exists()
    assert capsys.readouterr().err.strip() == "Invalid evaluation CLI input"


@pytest.mark.parametrize(
    "selection_data",
    [
        "{",
        json.dumps({"scenarios": []}),
        json.dumps(
            {
                "scenarios": [
                    {"scenario_id": "C01", "repeats": [1]},
                    {"scenario_id": "C01", "repeats": [2]},
                ]
            }
        ),
        json.dumps({"scenarios": [{"scenario_id": "C01", "repeats": [1, 1]}]}),
        json.dumps({"scenarios": [{"scenario_id": "C26", "repeats": [1]}]}),
        json.dumps({"scenarios": [{"scenario_id": "C01", "repeats": [4]}]}),
        json.dumps({"scenarios": [{"scenario_id": "C01", "repeats": [True]}]}),
    ],
)
def test_invalid_selection_is_rejected_before_factory_or_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    selection_data: str,
) -> None:
    selection_file = tmp_path / "selection.json"
    selection_file.write_text(selection_data, encoding="utf-8")
    out = tmp_path / "out"
    factory_calls: list[tuple[str, int, int]] = []

    def provider_for(scenario: Scenario, repeat: int, index: int) -> LLMProvider:
        factory_calls.append((scenario.id, repeat, index))
        return cli.GoldFollowingProvider(scenario.turns[index - 1])

    args = _argv(
        out,
        **{
            "--selection-file": str(selection_file),
            "--max-chat-turns": "22",
        },
    )
    assert cli.main(args, fixture_provider_for=provider_for) == 2
    assert factory_calls == []
    assert not out.exists()
    assert capsys.readouterr().err.strip() == "Invalid evaluation CLI input"


@pytest.mark.parametrize("cap", ["true", "invalid", "0", "-1", "21"])
def test_invalid_cap_is_rejected_before_factory_or_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], cap: str
) -> None:
    out = tmp_path / "out"
    factory_calls: list[tuple[str, int, int]] = []

    def provider_for(scenario: Scenario, repeat: int, index: int) -> LLMProvider:
        factory_calls.append((scenario.id, repeat, index))
        return cli.GoldFollowingProvider(scenario.turns[index - 1])

    args = _argv(
        out,
        **{"--selection-file": str(_SELECTION), "--max-chat-turns": cap},
    )
    assert cli.main(args, fixture_provider_for=provider_for) == 2
    assert factory_calls == []
    assert not out.exists()
    assert capsys.readouterr().err.strip() == "Invalid evaluation CLI input"


def test_selection_requires_a_cap_before_factory_or_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"
    factory_calls: list[tuple[str, int, int]] = []

    def provider_for(scenario: Scenario, repeat: int, index: int) -> LLMProvider:
        factory_calls.append((scenario.id, repeat, index))
        return cli.GoldFollowingProvider(scenario.turns[index - 1])

    args = _argv(out, **{"--selection-file": str(_SELECTION)})
    assert cli.main(args, fixture_provider_for=provider_for) == 2
    assert factory_calls == []
    assert not out.exists()
    assert capsys.readouterr().err.strip() == "Invalid evaluation CLI input"


def test_cap_parser_rejects_a_boolean() -> None:
    with pytest.raises(ValueError):
        cli._parse_max_chat_turns(True)


def test_an_existing_output_dir_is_rejected_and_left_untouched(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "keep.txt").write_text("keep", encoding="utf-8")
    assert cli.main(_argv(out)) == 2
    assert [path.name for path in out.iterdir()] == ["keep.txt"]
    assert capsys.readouterr().err.strip() == "Invalid evaluation CLI input"


def test_live_bedrock_and_fixture_together_are_rejected(tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert cli.main([*_argv(out), "--live-bedrock"]) == 2
    assert not out.exists()


def test_one_of_live_bedrock_or_fixture_is_required(tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert cli.main(_argv(out)[:-1]) == 2
    assert not out.exists()


class _FakeBedrock:
    created: list[tuple[str, str | None]] = []

    def __init__(
        self,
        model_id: str,
        *,
        region: str | None = None,
        profile_name: str | None = None,
    ) -> None:
        self.created.append((model_id, region))

    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        message = {"role": "assistant", "content": [{"text": "Which meal?"}]}
        usage = {"inputTokens": 5, "outputTokens": 2}
        output = {"message": message}
        return {"output": output, "stopReason": "end_turn", "usage": usage}


def _live_argv(out: Path, profile: str) -> list[str]:
    return [*_argv(out, **{"--profile": profile})[:-1], "--live-bedrock"]


def test_live_mode_warns_once_for_an_unverified_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _FakeBedrock.created = []
    monkeypatch.setattr(bedrock, "BedrockConverseProvider", _FakeBedrock)
    out = tmp_path / "out"
    assert cli.main(_live_argv(out, "nova-2-pro")) == 0
    err = capsys.readouterr().err.strip().splitlines()
    assert err == [cli._UNVERIFIED]
    assert _FakeBedrock.created == [("us.amazon.nova-2-pro-v1:0", "us-east-1")]
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["manifest"]["evidence_class"] == "real_bedrock"


def test_live_mode_is_silent_for_a_verified_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _FakeBedrock.created = []
    monkeypatch.setattr(bedrock, "BedrockConverseProvider", _FakeBedrock)
    assert cli.main(_live_argv(tmp_path / "out", "nova-2-lite")) == 0
    assert capsys.readouterr().err == ""
    assert _FakeBedrock.created == [("us.amazon.nova-2-lite-v1:0", "us-east-1")]


_LUNA_RATES = (
    Path(__file__).resolve().parents[2]
    / "eval/experiments/conversation-quality/luna-us-rates.json"
)


def _openai_argv(out: Path) -> list[str]:
    return [
        *_argv(
            out,
            **{
                "--profile": "gpt-6-luna",
                "--region": "us",
                "--rates": str(_LUNA_RATES),
                "--max-chat-turns": "123",
            },
        )[:-1],
        "--live-openai",
    ]


@pytest.mark.parametrize("region", ["us", "global"])
def test_luna_profile_has_fixed_responses_settings(region: str) -> None:
    profile = resolve_profile("gpt-6-luna", region)
    assert profile.model_config == {
        "reasoning_effort": "none",
        "max_output_tokens": 4096,
        "store": False,
        "parallel_tool_calls": False,
    }
    assert resolve_profile("nova-2-lite", "us-east-1").model_config == {
        "max_tokens": 4096,
        "temperature": 0,
        "reasoning_effort": "low",
    }


@pytest.mark.parametrize("missing", ["--rates", "--max-chat-turns"])
def test_openai_requires_rates_and_explicit_cap_before_factory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    missing: str,
) -> None:
    def forbidden(region: str) -> cli.ProviderFor:
        pytest.fail("The provider factory MUST NOT run.")

    monkeypatch.setattr(cli, "_openai_provider_for", forbidden)
    out = tmp_path / "out"
    args = _openai_argv(out)
    index = args.index(missing)
    del args[index : index + 2]
    assert cli.main(args) == 2
    assert not out.exists()


@pytest.mark.parametrize("openai", [True, False])
def test_transport_mismatch_fails_before_either_factory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    openai: bool,
) -> None:
    def forbidden(*args: object) -> cli.ProviderFor:
        pytest.fail("The provider factory MUST NOT run.")

    monkeypatch.setattr(cli, "_openai_provider_for", forbidden)
    monkeypatch.setattr(cli, "_live_provider_for", forbidden)
    out = tmp_path / "out"
    args = _openai_argv(out) if openai else _live_argv(out, "nova-2-lite")
    args[-1] = "--live-bedrock" if openai else "--live-openai"
    assert cli.main(args) == 2
    assert not out.exists()


def test_openai_fixture_excludes_live_modes(tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert cli.main([*_openai_argv(out), "--fixture"]) == 2
    assert cli.main([*_openai_argv(out), "--live-bedrock"]) == 2
    assert not out.exists()


def test_openai_uses_lazy_provider_and_records_real_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[tuple[Path, str]] = []

    class FakeOpenAI(_FakeBedrock):
        def __init__(self, key: Path, *, region: str = "us") -> None:
            created.append((key, region))

        def converse(
            self,
            system_prompt: str,
            messages: list[dict[str, object]],
            tools: list[dict[str, object]],
        ) -> dict[str, object]:
            response = super().converse(system_prompt, messages, tools)
            response["usage"] = {
                "inputTokens": 5,
                "outputTokens": 2,
                "cacheReadInputTokens": 3,
            }
            return response

    module = ModuleType("app.providers.openai_responses")
    monkeypatch.setattr(module, "OpenAIResponsesProvider", FakeOpenAI, raising=False)
    monkeypatch.setitem(sys.modules, module.__name__, module)
    key = tmp_path / "unread-key"
    monkeypatch.setenv("FEWIA_OPENAI_API_KEY_FILE", str(key))
    out = tmp_path / "out"
    assert cli.main(_openai_argv(out)) == 0
    assert created == [(key, "us")]
    assert not key.exists()
    report = json.loads((out / "report.json").read_bytes())
    assert report["manifest"]["evidence_class"] == "real_openai"
    assert report["manifest"]["model_id"] == "gpt-6-luna"
    assert report["manifest"]["rates"]["cached_input_usd_per_1000"] == "0.000011"
    assert report["cost"]["cache_read_tokens"] > 0
    assert report["cost"]["input_tokens"] > report["cost"]["cache_read_tokens"]
    assert report["cost"]["coverage_complete"] is True


def test_tool_hash_includes_proposal_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    original = cli.tool_specs_hash()
    monkeypatch.setattr(chat_loop, "proposal_tool_spec", lambda: {"changed": True})
    assert cli.tool_specs_hash() != original


def test_openai_rejects_wrong_rate_region_before_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(region: str) -> cli.ProviderFor:
        pytest.fail("The provider factory MUST NOT run.")

    monkeypatch.setattr(cli, "_openai_provider_for", forbidden)
    out = tmp_path / "out"
    args = _openai_argv(out)
    args[args.index("--region") + 1] = "global"
    assert cli.main(args) == 2
    assert not out.exists()
