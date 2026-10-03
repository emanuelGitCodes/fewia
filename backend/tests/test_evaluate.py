import builtins
import hashlib
import json
import runpy
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn, cast
from unittest.mock import Mock

import pytest

from app import evaluate
from app import evaluation_batch as batch
from app import evaluation_cli_config as config
from app import evaluation_markdown as markdown
from app.agent.provider import LLMProvider
from app.evaluation_io import EvaluationOutput
from app.evaluation_matrix import EvaluationSlot, prepare_matrix
from app.evaluation_runtime import EvaluationRuntime

CORPUS = Path(__file__).parent / "evaluation" / "scenarios.json"
REVISION = "a" * 40
MODEL_ID = "us.amazon.nova-2-lite-v1:0"
PRIVATE = "PRIVATE_RESPONSE_AND_ERROR_MARKER"


class FakeProvider:
    def __init__(self) -> None:
        self.calls = 0

    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        self.calls += 1
        answer = f"Which meals and servings would you like? {PRIVATE}"
        text = (
            answer
            if tools
            else json.dumps(
                {
                    "status": "clarification",
                    "answer": answer,
                    "request": None,
                    "plan": None,
                    "budget": None,
                }
            )
        )
        return {
            "stopReason": "end_turn",
            "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
            "usage": {"inputTokens": 5, "outputTokens": 7},
        }


@pytest.fixture
def argv(tmp_path: Path) -> list[str]:
    return [
        "--corpus",
        str(CORPUS),
        "--output-dir",
        str(tmp_path / "output"),
        "--revision",
        REVISION,
    ]


def _rows(directory: Path) -> list[dict[str, object]]:
    raw = (directory / "slots.jsonl").read_bytes()
    assert raw.endswith(b"\n")
    return [cast(dict[str, object], json.loads(line)) for line in raw.splitlines()]


def _map(value: object) -> dict[str, object]:
    assert type(value) is dict
    return cast(dict[str, object], value)


def test_full_fake_run_journals_before_progress_and_finishes(
    argv: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    directory = Path(argv[3])
    providers: list[FakeProvider] = []
    seen: list[dict[str, object]] = []
    real_print = evaluate._print_progress

    def factory() -> LLMProvider:
        assert (directory / "slots.jsonl").exists()
        provider = FakeProvider()
        providers.append(provider)
        return provider

    def progress(slot: dict[str, object]) -> None:
        seen.append(slot)
        assert _rows(directory) == seen
        real_print(slot)

    monkeypatch.setattr(evaluate, "_print_progress", progress)
    assert evaluate.main(argv, provider_factory=factory) == 0
    rows = _rows(directory)
    assert len(rows) == len(seen) == 138
    options = config.load_options(argv, fixture=True)
    matrix = prepare_matrix(options.corpus)
    assert [(r["case_id"], r["repeat"], r["condition"]) for r in rows] == [
        (s.case_id, s.repeat, s.condition) for s in matrix
    ]
    applicable = [row for row in rows if row["driver"] in ("model", "no_tool")]
    assert len(providers) == len(applicable) == 66
    assert len({id(provider) for provider in providers}) == 66
    assert all(provider.calls > 0 for provider in providers)
    for row in applicable:
        observation = _map(row["observation"])
        assert observation["model_id"] == MODEL_ID
        assert observation["evidence_class"] == "deterministic_fake_provider"
    duplicate = [row for row in rows if row["case_id"] == "P05"]
    assert len(duplicate) == 3
    assert all(row["status"] == "unassessed" for row in duplicate)
    assert all(
        _map(row["observation"])["reason_code"] == "missing_local_services"
        for row in duplicate
    )
    report = _map(json.loads((directory / "report.json").read_text()))
    assert report["total_slot_count"] == 138
    assert report["revision"] == REVISION
    assert report["metrics_status"] == "partial"
    manifest = _map(report["manifest"])
    assert manifest["model_id"] == MODEL_ID
    assert manifest["region"] == "us-east-1"
    assert manifest["model_config"] == {
        "max_tokens": 4096,
        "temperature": 0,
        "reasoning_effort": "low",
    }
    marker = _map(json.loads((directory / "completion.json").read_text()))
    assert marker["slot_count"] == 138
    assert marker["sha256"] == {
        name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
        for name in ("report.json", "report.md")
    }
    rendered = (directory / "report.md").read_text()
    assert (
        "Deterministic fixture, reference, and fake evidence "
        "does not establish real-model quality." in rendered
    )
    assert "does not establish real-model quality" in rendered
    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert len(lines) == 141
    assert lines[-3:] == [
        str(directory / name)
        for name in ("report.json", "report.md", "completion.json")
    ]
    for line in lines[:-3]:
        assert [field.split("=", 1)[0] for field in line.split()] == [
            "case_id",
            "repeat",
            "condition",
            "status",
        ]
        assert len(line) < 100
    assert PRIVATE not in captured.out + captured.err
    assert captured.err == ""


@pytest.mark.parametrize("injected", [False, True])
def test_invalid_opt_in_fails_before_inputs_output_or_provider(
    argv: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    injected: bool,
) -> None:
    factory = Mock(side_effect=AssertionError("provider constructed"))
    read = Mock(side_effect=AssertionError("input read"))
    monkeypatch.setattr(config, "load_json", read)
    if injected:
        argv.append("--live-bedrock")
    assert evaluate.main(argv, provider_factory=factory if injected else None) == 1
    factory.assert_not_called()
    read.assert_not_called()
    assert not Path(argv[3]).exists()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Evaluation failed\n"


@pytest.mark.parametrize("kind", ["directory", "file", "symlink", "dangling"])
def test_existing_output_prevents_factory_and_dispatch(
    argv: list[str], monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    directory = Path(argv[3])
    target = directory.parent / "target"
    if kind == "directory":
        directory.mkdir()
    elif kind == "file":
        directory.write_text("preserved")
    else:
        if kind == "symlink":
            target.mkdir()
        directory.symlink_to(target)
    factory = Mock(side_effect=AssertionError("provider constructed"))
    runner = Mock(side_effect=AssertionError("batch dispatched"))
    monkeypatch.setattr(batch, "run_evaluation_batch", runner)
    assert evaluate.main(argv, provider_factory=factory) == 1
    factory.assert_not_called()
    runner.assert_not_called()
    assert directory.exists() or directory.is_symlink()
    if kind == "file":
        assert directory.read_text() == "preserved"


def test_live_factory_uses_validated_options_and_fresh_providers(
    argv: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.providers import bedrock

    directory = Path(argv[3])
    providers: list[FakeProvider] = []

    def construct(
        model_id: str, *, region: str, profile_name: str | None
    ) -> FakeProvider:
        assert (directory / "slots.jsonl").exists()
        assert model_id == MODEL_ID
        assert region == "us-west-2"
        assert profile_name == "test-profile"
        provider = FakeProvider()
        providers.append(provider)
        return provider

    monkeypatch.setenv("AWS_PROFILE", "test-profile")
    monkeypatch.setattr(bedrock, "BedrockConverseProvider", construct)
    argv.extend(["--live-bedrock", "--region", "us-west-2"])
    assert evaluate.main(argv) == 0
    assert len(providers) == len({id(provider) for provider in providers}) == 66
    rows = _rows(directory)
    for row in rows:
        if row["driver"] in ("model", "no_tool"):
            assert _map(row["observation"])["evidence_class"] == "real_bedrock"


def test_interrupt_during_slot_50_preserves_49_rows(
    argv: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = 0
    real_run_slot = batch.run_slot

    def interrupt(
        slot: EvaluationSlot, runtime: EvaluationRuntime
    ) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 50:
            raise KeyboardInterrupt
        return real_run_slot(slot, runtime)

    monkeypatch.setattr(batch, "run_slot", interrupt)
    assert evaluate.main(argv, provider_factory=FakeProvider) == 130
    directory = Path(argv[3])
    assert len(_rows(directory)) == 49
    assert calls == 50
    assert not (directory / "completion.json").exists()
    assert not (directory / "report.json").exists()
    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == 49
    assert captured.err == "Evaluation interrupted\n"


@pytest.mark.parametrize("stage", ["batch", "render", "report_write", "journal_write"])
def test_failures_preserve_journal_without_completion(
    argv: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    stage: str,
) -> None:
    def fail(*args: object, **kwargs: object) -> NoReturn:
        raise OSError(f"{PRIVATE} https://private.example/response")

    if stage == "batch":
        monkeypatch.setattr(batch, "run_evaluation_batch", fail)
    elif stage == "render":
        monkeypatch.setattr(markdown, "render_report", fail)
    elif stage == "report_write":
        monkeypatch.setattr(EvaluationOutput, "_write", fail)
    else:
        append = EvaluationOutput.append_slot
        calls = 0

        def append_or_fail(output: EvaluationOutput, slot: dict[str, object]) -> None:
            nonlocal calls
            calls += 1
            if calls == 4:
                fail()
            append(output, slot)

        monkeypatch.setattr(EvaluationOutput, "append_slot", append_or_fail)
    assert evaluate.main(argv, provider_factory=FakeProvider) == 1
    directory = Path(argv[3])
    expected = {
        "batch": 0,
        "journal_write": 3,
        "render": 138,
        "report_write": 138,
    }[stage]
    if expected:
        assert len(_rows(directory)) == expected
    else:
        assert (directory / "slots.jsonl").read_bytes() == b""
    assert not (directory / "completion.json").exists()
    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == expected
    assert captured.err == "Evaluation failed\n"
    assert PRIVATE not in captured.out + captured.err
    assert "https://" not in captured.out + captured.err


def test_validated_rates_reach_real_renderer(
    argv: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    rates: dict[str, object] = {
        "model_id": MODEL_ID,
        "region": "us-east-1",
        "currency": "USD",
        "input_usd_per_1000": "0.0003300000",
        "output_usd_per_1000": "0.0027500000",
        "source_url": "https://pricing.us-east-1.amazonaws.com/index.json",
        "source_version": "test-rates-v1",
        "published_at": "2026-09-30T23:02:55Z",
        "effective_date": "2026-09-01",
        "retrieved_at": "2026-10-02",
    }
    path = Path(argv[3]).parent / "rates.json"
    path.write_text(json.dumps(rates))
    renderer = Mock(wraps=markdown.render_report)
    monkeypatch.setattr(markdown, "render_report", renderer)
    result = evaluate.main(argv + ["--rates", str(path)], provider_factory=FakeProvider)
    assert result == 0
    renderer.assert_called_once()
    assert renderer.call_args.kwargs == {"rates": rates}
    assert (Path(argv[3]) / "completion.json").exists()


def test_factory_errors_complete_artifacts_without_leaking_details(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    def factory() -> NoReturn:
        raise RuntimeError(PRIVATE)

    assert evaluate.main(argv, provider_factory=factory) == 0
    directory = Path(argv[3])
    rows = _rows(directory)
    assert len(rows) == 138
    assert all(
        row["status"] == "failed"
        for row in rows
        if row["driver"] in ("model", "no_tool")
    )
    assert (directory / "completion.json").exists()
    captured = capsys.readouterr()
    assert PRIVATE not in captured.out + captured.err
    assert captured.err == ""


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("case_id", PRIVATE),
        ("case_id", "B01\nPRIVATE"),
        ("repeat", PRIVATE),
        ("repeat", True),
        ("repeat", 4),
        ("condition", PRIVATE),
        ("status", PRIVATE),
    ],
)
def test_progress_rejects_unbounded_values(
    key: str, value: object, capsys: pytest.CaptureFixture[str]
) -> None:
    slot: dict[str, object] = {
        "case_id": "B01",
        "repeat": 1,
        "condition": "deterministic_fixture",
        "status": "completed",
        "answer": PRIVATE,
        "exception": PRIVATE,
        "url": "https://private.example/response",
    }
    slot[key] = value
    evaluate._print_progress(slot)
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


@pytest.mark.parametrize("exception", [SystemExit, GeneratorExit])
def test_unrelated_process_exceptions_propagate(
    argv: list[str], monkeypatch: pytest.MonkeyPatch, exception: type[BaseException]
) -> None:
    def fail(*args: object, **kwargs: object) -> NoReturn:
        raise exception

    monkeypatch.setattr(batch, "run_evaluation_batch", fail)
    with pytest.raises(exception):
        evaluate.main(argv, provider_factory=FakeProvider)
    assert not (Path(argv[3]) / "completion.json").exists()


def test_import_and_module_help_are_lazy(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    real_import = builtins.__import__

    def checked_import(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        assert name not in {
            "boto3",
            "app.providers.bedrock",
            "app.evaluation_batch",
            "app.evaluation_markdown",
            "app.evaluation_runtime",
        }
        return real_import(name, globals, locals, fromlist, level)

    def forbidden(*args: object, **kwargs: object) -> NoReturn:
        raise AssertionError("help performed work")

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "__import__", checked_import)
        patch.setattr(config, "load_json", forbidden)
        patch.setattr(Path, "mkdir", forbidden)
        patch.setattr(EvaluationOutput, "__enter__", forbidden)
        namespace = runpy.run_path(str(Path(evaluate.__file__)))
        main = cast(Callable[..., int], namespace["main"])
        with pytest.raises(SystemExit) as help_exit:
            main(["--help"], provider_factory=forbidden)
        assert help_exit.value.code == 0
        patch.setattr(sys, "argv", ["app.evaluate", "--help"])
        with pytest.raises(SystemExit) as module_exit:
            runpy.run_path(str(Path(evaluate.__file__)), run_name="__main__")
        assert module_exit.value.code == 0
    captured = capsys.readouterr()
    assert "--live-bedrock" in captured.out
    assert "--fixture" not in captured.out
    assert captured.err == ""
