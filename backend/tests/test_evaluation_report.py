from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from app.evaluate import main as evaluate_main
from app.evaluation_io import FILE_UNAVAILABLE, OUTPUT_EXISTS
from app.evaluation_report import main
from app.evaluation_report_values import INVALID

DIGEST = "0123456789abcdef0123456789abcdef01234567"
HASH64 = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
SECRET = "do-not-echo-raw-input"
FAKE = "deterministic_fake_provider"
MAX = 16 * 1024 * 1024
_INTERRUPT = "evaluation report interrupted"
_FAIL = "evaluation report failed"


def _slot() -> dict[str, object]:
    return {
        "status": "scored",
        "report": {"checks": {"accepted": True}, "evidence_class": FAKE},
    }


def _payload(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "metrics_status": "unassessed",
        "revision": DIGEST,
        "model_id": "eval-fake-v1",
        "source_region": "us-east-1",
        "slots": [_slot()],
        "prompt_hash": HASH64,
        "catalog_version": "sample-prices-v1",
        "quality_note": SECRET,
        "answers": {"P04": SECRET},
        "success_rate": "100%",
    }
    body.update(overrides)
    return body


def _write(path: Path, body: dict[str, object]) -> None:
    path.write_text(json.dumps(body), encoding="utf-8")


def _argv(source: Path, output: Path) -> list[str]:
    return ["--input", str(source), "--output", str(output)]


def _static(text: str, *paths: Path) -> None:
    assert "Traceback" not in text
    assert SECRET not in text
    for path in paths:
        assert str(path) not in text
        assert path.name not in text


def _ok(capsys: pytest.CaptureFixture[str], *paths: Path) -> str:
    captured = capsys.readouterr()
    assert captured.err == ""
    _static(captured.out, *paths)
    return captured.out


def _fail(capsys: pytest.CaptureFixture[str], expected: str, *paths: Path) -> None:
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == expected
    _static(captured.err, *paths)


def _provider_boom(*_a: object, **_k: object) -> None:
    raise AssertionError("provider")


def test_saved_fixture_writes_markdown_and_safe_counts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "batch.json"
    output = tmp_path / "report.md"
    _write(source, _payload())
    original = source.read_bytes()
    assert main(_argv(source, output)) == 0
    text = output.read_text(encoding="utf-8")
    out = _ok(capsys, source, output)
    assert "evaluation report written" in out
    assert "slots: 1" in out
    assert f"Revision: {DIGEST}" in text
    assert "Model: `eval-fake-v1`" in text
    assert "Source region: `us-east-1`" in text
    assert f"Prompt hash: {HASH64}" in text
    assert "Catalog version: `sample-prices-v1`" in text
    assert "Global quality: UNASSESSED" in text
    assert "| 1 | 0 | 0 | 0 | 0 |" in text
    assert SECRET not in text
    assert "P04" not in text
    assert "100%" not in text
    assert "quality_note" not in text
    assert "success_rate" not in text
    assert source.read_bytes() == original
    assert not source.with_suffix(".jsonl").exists()
    assert not output.with_name(output.name + ".tmp").exists()


def test_partial_slots_unknown_region_and_empty_batch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "batch.json"
    output = tmp_path / "report.md"
    _write(
        source,
        _payload(
            model_id="eval-fake-v1",
            source_region=None,
            slots=[_slot(), {"status": "broken"}],
            prompt_hash=None,
            catalog_version=None,
        ),
    )
    assert main(_argv(source, output)) == 0
    text = output.read_text(encoding="utf-8")
    assert "Source region: not recorded" in text
    assert "Prompt hash:" not in text
    assert "Catalog version:" not in text
    assert "| 1 | 0 | 0 | 0 | 1 |" in text
    assert "Global quality: UNASSESSED" in text
    assert "slots: 2" in _ok(capsys, source, output)
    empty = tmp_path / "empty.json"
    empty_out = tmp_path / "empty.md"
    _write(
        empty,
        _payload(
            model_id=None,
            source_region=None,
            slots=[],
            prompt_hash=None,
            catalog_version=None,
        ),
    )
    assert main(_argv(empty, empty_out)) == 0
    empty_text = empty_out.read_text(encoding="utf-8")
    assert "Model: not recorded" in empty_text
    assert "Source region: not recorded" in empty_text
    assert "| 0 | 0 | 0 | 0 | 0 |" in empty_text
    assert "slots: 0" in _ok(capsys, empty, empty_out)


def test_forbidden_quality_claim_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / f"{SECRET}.json"
    output = tmp_path / "report.md"
    _write(source, _payload(metrics_status="passed"))
    assert main(_argv(source, output)) == 1
    _fail(capsys, INVALID, source, output)
    assert not output.exists()


def _bad_revision(body: dict[str, object]) -> None:
    body["revision"] = DIGEST.upper()


def _bad_label(body: dict[str, object]) -> None:
    body["model_id"] = f"x\n{SECRET}"


def _bad_hash(body: dict[str, object]) -> None:
    body["prompt_hash"] = "abc"


def _metadata_only(body: dict[str, object]) -> None:
    body["metadata"] = {
        "revision": body.pop("revision"),
        "model_id": body.pop("model_id"),
        "source_region": body.pop("source_region"),
    }


@pytest.mark.parametrize(
    ("mutate", "raw"),
    [
        (_bad_revision, None),
        (_bad_label, None),
        (_bad_hash, None),
        (_metadata_only, None),
        (None, "{" + SECRET),
    ],
)
def test_malformed_revision_labels_hash_and_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    mutate: Callable[[dict[str, object]], None] | None,
    raw: str | None,
) -> None:
    source = tmp_path / f"{SECRET}.json"
    output = tmp_path / "report.md"
    if mutate is not None:
        body = _payload()
        mutate(body)
        _write(source, body)
    else:
        assert raw is not None
        source.write_text(raw, encoding="utf-8")
    assert main(_argv(source, output)) == 1
    _fail(capsys, INVALID, source, output)
    assert not output.exists()


def test_oversize_input_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / f"{SECRET}.json"
    output = tmp_path / "report.md"
    source.write_bytes(b"x" * (MAX + 1))
    assert main(_argv(source, output)) == 1
    _fail(capsys, INVALID, source, output)
    assert not output.exists()


def test_missing_file_uses_static_error_without_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / f"{SECRET}.json"
    output = tmp_path / "report.md"
    assert main(_argv(source, output)) == 1
    _fail(capsys, FILE_UNAVAILABLE, source, output)
    assert not output.exists()


def test_nonregular_input_and_help(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "report.md"
    assert main(_argv(tmp_path, output)) == 1
    _fail(capsys, INVALID, tmp_path, output)
    assert not output.exists()
    assert main([]) == 1
    _fail(capsys, INVALID)
    assert main(["--help"]) == 0
    help_text = _ok(capsys)
    assert "--input" in help_text
    assert "--output" in help_text


def test_existing_output_is_preserved(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "batch.json"
    output = tmp_path / "report.md"
    _write(source, _payload())
    output.write_text("keep\n", encoding="utf-8")
    assert main(_argv(source, output)) == 1
    _fail(capsys, OUTPUT_EXISTS, source, output)
    assert output.read_text(encoding="utf-8") == "keep\n"
    same = tmp_path / "same.md"
    _write(same, _payload())
    before = same.read_bytes()
    assert main(_argv(same, same)) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() in {INVALID, OUTPUT_EXISTS}
    _static(captured.err, same)
    assert same.read_bytes() == before


def test_provider_builders_are_not_called(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[str] = []

    def mark(name: str) -> Callable[..., None]:
        def inner(*_a: object, **_k: object) -> None:
            calls.append(name)

        return inner

    monkeypatch.setattr("app.provider_runtime.build_bedrock", mark("bedrock"))
    monkeypatch.setattr("app.provider_runtime.build_plaid", mark("plaid"))
    monkeypatch.setattr("app.provider_runtime.build_instacart", mark("instacart"))
    monkeypatch.setattr("app.evaluation_batch.run_observed_evaluation", mark("observe"))
    source = tmp_path / "batch.json"
    output = tmp_path / "report.md"
    _write(source, _payload())
    assert main(_argv(source, output)) == 0
    _ok(capsys, source, output)
    assert calls == []
    assert output.exists()


def test_keyboard_interrupt_and_static_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / f"{SECRET}.json"
    output = tmp_path / "report.md"
    _write(source, _payload())

    def boom(_path: Path) -> dict[str, object]:
        raise KeyboardInterrupt

    monkeypatch.setattr("app.evaluation_report._load", boom)
    assert main(_argv(source, output)) == 130
    _fail(capsys, _INTERRUPT, source, output)
    assert not output.exists()

    def fail(_path: Path) -> dict[str, object]:
        raise RuntimeError(f"Traceback {SECRET}")

    monkeypatch.setattr("app.evaluation_report._load", fail)
    assert main(_argv(source, output)) == 1
    _fail(capsys, _FAIL, source, output)
    assert not output.exists()


@pytest.mark.parametrize(
    ("target", "kind", "expected"),
    [
        ("_load", "value", INVALID),
        ("_render", "value", INVALID),
        ("write_markdown", "value", INVALID),
        ("_load", "os", FILE_UNAVAILABLE),
        ("_render", "os", FILE_UNAVAILABLE),
        ("write_markdown", "os", FILE_UNAVAILABLE),
        ("write_markdown", "exists", OUTPUT_EXISTS),
    ],
)
def test_injected_boundary_errors_stay_static(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    target: str,
    kind: str,
    expected: str,
) -> None:
    source = tmp_path / f"{SECRET}.json"
    output = tmp_path / "report.md"
    _write(source, _payload())
    marker = f"Traceback {SECRET} {source}"

    def boom(*_a: object, **_k: object) -> None:
        if kind == "value":
            raise ValueError(marker)
        if kind == "exists":
            raise OSError(OUTPUT_EXISTS)
        raise OSError(marker)

    monkeypatch.setattr(f"app.evaluation_report.{target}", boom)
    assert main(_argv(source, output)) == 1
    _fail(capsys, expected, source, output)
    assert not output.exists()


def test_fixture_producer_feeds_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("app.evaluate.build_bedrock", _provider_boom)
    monkeypatch.setattr("app.provider_runtime.build_bedrock", _provider_boom)
    monkeypatch.setattr("app.provider_runtime.build_plaid", _provider_boom)
    monkeypatch.setattr("app.provider_runtime.build_instacart", _provider_boom)
    batch = tmp_path / "batch.json"
    output = tmp_path / "report.md"
    code = evaluate_main(
        ["--mode", "fixture", "--revision", DIGEST, "--output", str(batch)]
    )
    assert code == 0
    capsys.readouterr()
    original = batch.read_bytes()
    body = json.loads(original.decode("utf-8"))
    assert "metadata" not in body
    assert body["revision"] == DIGEST
    assert main(_argv(batch, output)) == 0
    text = output.read_text(encoding="utf-8")
    out = _ok(capsys, batch, output)
    assert "slots: 90" in out
    assert "| 51 | 0 | 0 | 39 | 0 |" in text
    assert "Source region: not recorded" in text
    assert batch.read_bytes() == original
