from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TextIO, cast

import pytest

from app.agent.chat_loop import SYSTEM_PROMPT
from app.agent.provider import LLMProvider
from app.domain.catalog import CATALOG_VERSION
from app.evaluate import main
from app.evaluation_batch import INVALID, _digest, _snapshot
from app.evaluation_io import FILE_UNAVAILABLE, OUTPUT_EXISTS, write_record
from app.provider_settings import (
    GroceryProviderSettings,
    ProviderConfigurationError,
)

CORPUS = Path(__file__).parent / "evaluation" / "scenarios.json"
REV = "a" * 40
SECRET = "do-not-echo-raw-input"
ARG = "evaluation arguments are invalid"
FAIL = "evaluation failed"
CONFIG = "Provider configuration is invalid"
MODEL = "eval-fake-v1"
OBSERVED = 24


@pytest.fixture(autouse=True)
def _clear_fewia_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.startswith("FEWIA_"):
            monkeypatch.delenv(name, raising=False)


class ScriptedProvider:
    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        return {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [{"text": "Choose a supported meal."}],
                }
            },
            "stopReason": "end_turn",
            "usage": {"inputTokens": 1, "outputTokens": 1},
        }


def _cli(output: Path, extra: list[str] | None = None) -> list[str]:
    args = ["--output", str(output), "--revision", REV, "--corpus", str(CORPUS)]
    return extra + args if extra is not None else args


def _safe(text: str, *markers: object) -> None:
    for marker in markers:
        assert str(marker) not in text


def _journal(output: Path) -> Path:
    return output.with_suffix(".jsonl")


def _rows(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _provider_boom(*_a: object, **_k: object) -> None:
    raise AssertionError("provider")


def _install_bedrock(
    monkeypatch: pytest.MonkeyPatch, providers: list[ScriptedProvider]
) -> None:
    settings = GroceryProviderSettings(bedrock_model_id=MODEL)

    def load() -> GroceryProviderSettings:
        return settings

    def build(_settings: GroceryProviderSettings) -> LLMProvider:
        provider = ScriptedProvider()
        providers.append(provider)
        return provider

    monkeypatch.setattr("app.evaluate.load_provider_settings", load)
    monkeypatch.setattr("app.evaluate.build_bedrock", build)


def test_help_returns_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--help"]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "--mode" in captured.out


def test_main_none_uses_sys_argv(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["evaluate", "--help"])
    assert main() == 0
    assert capsys.readouterr().err == ""


def test_default_fixture_skips_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("app.evaluate.load_provider_settings", _provider_boom)
    monkeypatch.setattr("app.evaluate.build_bedrock", _provider_boom)
    output = tmp_path / "out.json"
    assert main(["--output", str(output), "--revision", REV]) == 0
    body = json.loads(output.read_text(encoding="utf-8"))
    journal = _rows(_journal(output))
    summary = json.loads(capsys.readouterr().out)
    corpus_hash, _working = _snapshot(
        cast(dict[str, object], json.loads(CORPUS.read_text(encoding="utf-8")))
    )
    assert body["mode"] == "fixture"
    assert body["requested_mode"] == "fixture"
    assert journal[0]["mode"] == "fixture"
    assert journal[0]["requested_mode"] == "fixture"
    assert body["revision"] == REV
    assert body["model_id"] is None
    assert body["source_region"] is None
    assert body["catalog_version"] == CATALOG_VERSION
    assert body["prompt_hash"] == _digest(SYSTEM_PROMPT)
    assert body["corpus_hash"] == corpus_hash
    assert body["metrics_status"] == "unassessed"
    assert journal[0]["model_id"] is None
    assert journal[0]["source_region"] is None
    assert journal[0]["revision"] == REV
    assert len(journal) == 91
    assert len(cast(list[object], body["slots"])) == 90
    assert summary == {
        "counts": {
            "scored": 48,
            "observed": 0,
            "unassessed": 42,
            "failed": 0,
        },
        "output": str(output),
        "metrics_status": "unassessed",
    }
    assert "slots" not in summary
    blob = json.dumps(summary)
    assert "Choose a supported meal." not in blob
    assert SECRET not in blob


def test_invalid_mode_is_static(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / f"{SECRET}.json"
    code = main(_cli(output, ["--mode", "live"]))
    err = capsys.readouterr().err
    assert code == 2
    assert err == ARG + "\n"
    _safe(err, SECRET, output, "live")
    assert not output.exists()
    assert not _journal(output).exists()


@pytest.mark.parametrize("revision", [SECRET, "A" * 40, "a" * 39, "a" * 41])
def test_invalid_revision_is_static(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], revision: str
) -> None:
    output = tmp_path / f"{SECRET}.json"
    code = main(
        ["--output", str(output), "--revision", revision, "--corpus", str(CORPUS)]
    )
    captured = capsys.readouterr()
    assert code == 2
    assert captured.err == ARG + "\n"
    _safe(captured.out + captured.err, SECRET, revision, output)
    assert not output.exists()


def test_invalid_corpus_is_static(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "out.json"
    missing = tmp_path / f"{SECRET}.json"
    code = main(["--output", str(output), "--revision", REV, "--corpus", str(missing)])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err == FILE_UNAVAILABLE + "\n"
    _safe(captured.out + captured.err, SECRET, missing)
    bad = tmp_path / f"{SECRET}-bad.json"
    bad.write_text('{"id": "' + SECRET, encoding="utf-8")
    code = main(["--output", str(output), "--revision", REV, "--corpus", str(bad)])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err == INVALID + "\n"
    _safe(captured.out + captured.err, SECRET, bad)
    assert not output.exists()
    assert not _journal(output).exists()


def test_bedrock_config_errors_make_zero_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / f"{SECRET}.json"
    calls: list[int] = []

    def boom() -> GroceryProviderSettings:
        raise ProviderConfigurationError()

    def build(_settings: GroceryProviderSettings) -> LLMProvider:
        calls.append(1)
        raise AssertionError(SECRET)

    monkeypatch.setattr("app.evaluate.load_provider_settings", boom)
    monkeypatch.setattr("app.evaluate.build_bedrock", build)
    code = main(_cli(output, ["--mode", "bedrock"]))
    assert code == 1
    assert calls == []
    err = capsys.readouterr().err
    assert err == CONFIG + "\n"
    _safe(err, SECRET, output)
    assert not output.exists()
    assert not _journal(output).exists()

    def empty() -> GroceryProviderSettings:
        return GroceryProviderSettings()

    monkeypatch.setattr("app.evaluate.load_provider_settings", empty)
    code = main(_cli(output, ["--mode", "bedrock"]))
    captured = capsys.readouterr()
    assert code == 1
    assert calls == []
    assert captured.err == CONFIG + "\n"
    _safe(captured.out + captured.err, SECRET)
    assert not _journal(output).exists()


def test_mocked_bedrock_writes_fresh_providers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    providers: list[ScriptedProvider] = []
    _install_bedrock(monkeypatch, providers)
    output = tmp_path / "out.json"
    assert main(_cli(output, ["--mode", "bedrock"])) == 0
    body = json.loads(output.read_text(encoding="utf-8"))
    journal = _rows(_journal(output))
    summary = json.loads(capsys.readouterr().out)
    slots = [row for row in journal[1:]]
    assert len(providers) == OBSERVED
    assert len({id(item) for item in providers}) == OBSERVED
    assert len(journal) == 91
    assert len(slots) == 90
    assert journal[0]["mode"] == "mixed_fixture_model"
    assert journal[0]["requested_mode"] == "bedrock"
    assert journal[0]["model_id"] == MODEL
    assert journal[0]["source_region"] == "us-east-1"
    assert body["mode"] == "mixed_fixture_model"
    assert body["requested_mode"] == "bedrock"
    assert body["model_id"] == MODEL
    assert body["source_region"] == "us-east-1"
    assert body["revision"] == REV
    assert body["metrics_status"] == "unassessed"
    assert summary["counts"] == {
        "scored": 48,
        "observed": OBSERVED,
        "unassessed": 18,
        "failed": 0,
    }
    assert summary["metrics_status"] == "unassessed"
    assert "slots" not in summary
    assert "Choose a supported meal." not in json.dumps(summary)
    blob = json.dumps(body) + json.dumps(journal[0])
    assert SECRET not in blob
    assert "aws_profile" not in journal[0]
    assert "plaid_secret_file" not in journal[0]


def test_mocked_bedrock_copies_loaded_source_region(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    providers: list[ScriptedProvider] = []
    settings = GroceryProviderSettings(
        bedrock_model_id=MODEL, bedrock_region="us-west-2"
    )

    def load() -> GroceryProviderSettings:
        return settings

    def build(_settings: GroceryProviderSettings) -> LLMProvider:
        provider = ScriptedProvider()
        providers.append(provider)
        return provider

    monkeypatch.setattr("app.evaluate.load_provider_settings", load)
    monkeypatch.setattr("app.evaluate.build_bedrock", build)
    output = tmp_path / "out.json"
    assert main(_cli(output, ["--mode", "bedrock"])) == 0
    body = json.loads(output.read_text(encoding="utf-8"))
    journal = _rows(_journal(output))
    capsys.readouterr()
    assert body["source_region"] == "us-west-2"
    assert journal[0]["source_region"] == "us-west-2"
    assert "aws_profile" not in body
    assert providers != []


def test_existing_files_refuse_before_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    providers: list[ScriptedProvider] = []
    _install_bedrock(monkeypatch, providers)
    output = tmp_path / f"{SECRET}.json"
    journal = _journal(output)
    output.write_text("old-output\n", encoding="utf-8")
    code = main(_cli(output, ["--mode", "bedrock"]))
    captured = capsys.readouterr()
    assert code == 1
    assert providers == []
    assert captured.err == OUTPUT_EXISTS + "\n"
    _safe(captured.out + captured.err, SECRET, output)
    assert output.read_text(encoding="utf-8") == "old-output\n"
    assert not journal.exists()
    output.unlink()
    journal.write_text("old-journal\n", encoding="utf-8")
    code = main(_cli(output, ["--mode", "bedrock"]))
    captured = capsys.readouterr()
    assert code == 1
    assert providers == []
    assert captured.err == OUTPUT_EXISTS + "\n"
    assert journal.read_text(encoding="utf-8") == "old-journal\n"
    assert not output.exists()


def test_callback_write_failure_stops_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    providers: list[ScriptedProvider] = []
    _install_bedrock(monkeypatch, providers)
    output = tmp_path / "out.json"
    journal = _journal(output)

    def wrapped(handle: TextIO, payload: dict[str, object]) -> None:
        write_record(handle, payload)
        if payload.get("status") == "observed":
            raise OSError(SECRET)

    monkeypatch.setattr("app.evaluate.write_record", wrapped)
    code = main(_cli(output, ["--mode", "bedrock"]))
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err == FILE_UNAVAILABLE + "\n"
    _safe(captured.out + captured.err, SECRET, output)
    assert len(providers) == 1
    assert not output.exists()
    rows = _rows(journal)
    assert rows[0]["mode"] == "mixed_fixture_model"
    assert rows[0]["requested_mode"] == "bedrock"
    assert any(row.get("status") == "observed" for row in rows[1:])


def test_keyboard_interrupt_preserves_journal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "out.json"
    journal = _journal(output)

    def wrapped(handle: TextIO, payload: dict[str, object]) -> None:
        write_record(handle, payload)
        raise KeyboardInterrupt

    monkeypatch.setattr("app.evaluate.write_record", wrapped)
    monkeypatch.setattr("app.evaluate.load_provider_settings", _provider_boom)
    monkeypatch.setattr("app.evaluate.build_bedrock", _provider_boom)
    code = main(_cli(output))
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err == FAIL + "\n"
    assert not output.exists()
    rows = _rows(journal)
    assert rows[0]["mode"] == "fixture"
    assert rows[0]["requested_mode"] == "fixture"
    assert len(rows) == 2


def test_module_entrypoint_avoids_provider() -> None:
    text = Path(__file__).resolve().parents[1] / "app" / "evaluate.py"
    source = text.read_text(encoding="utf-8")
    assert 'if __name__ == "__main__":' in source
    assert "raise SystemExit(main())" in source
    assert "boto3" not in source
    assert "aws_access_key" not in source
    assert "--profile" not in source
    assert "--secret" not in source
