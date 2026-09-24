from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TextIO

import pytest

from app.domain.catalog import CATALOG_VERSION
from app.evaluation_batch import INVALID
from app.evaluation_io import (
    FILE_UNAVAILABLE,
    OUTPUT_EXISTS,
    load_corpus,
    open_journal,
    write_record,
    write_result,
)

CORPUS_PATH = Path(__file__).parent / "evaluation" / "scenarios.json"
SECRET = "do-not-echo-raw-input"
MARKER = "eval-io-marker-path-payload"


def _static(err: BaseException, path: Path) -> None:
    text = str(err)
    assert err.__cause__ is None
    assert SECRET not in text
    assert MARKER not in text
    assert str(path) not in text
    assert path.name not in text


def _temp(output: Path) -> Path:
    return output.with_name(output.name + ".tmp")


def _break_exclusive(
    monkeypatch: pytest.MonkeyPatch, *, flush: bool, interrupt: bool = False
) -> None:
    orig = Path.open

    def wrapped(self: Path, mode: str = "r", *args: object, **kwargs: object) -> TextIO:
        handle = orig(self, mode, *args, **kwargs)
        if "x" not in mode:
            return handle

        def boom(*_a: object, **_k: object) -> None:
            if interrupt:
                raise KeyboardInterrupt
            raise OSError(28)

        if flush:
            monkeypatch.setattr(handle, "flush", boom)
        else:
            monkeypatch.setattr(handle, "write", boom)
        return handle

    monkeypatch.setattr(Path, "open", wrapped)


def test_load_corpus_accepts_fixture() -> None:
    body = load_corpus(CORPUS_PATH)
    assert body["catalog_version"] == CATALOG_VERSION
    assert body["repeats"] == 3


def test_malformed_corpus_uses_static_valueerror(tmp_path: Path) -> None:
    path = tmp_path / f"{MARKER}.json"
    path.write_text('{"id": "' + SECRET, encoding="utf-8")
    with pytest.raises(ValueError, match=f"^{INVALID}$") as err:
        load_corpus(path)
    _static(err.value, path)


def test_invalid_corpus_fields_use_static_valueerror(tmp_path: Path) -> None:
    payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    payload["catalog_version"] = SECRET
    path = tmp_path / f"{MARKER}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match=f"^{INVALID}$") as err:
        load_corpus(path)
    _static(err.value, path)


def test_nan_corpus_uses_static_valueerror(tmp_path: Path) -> None:
    payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    payload["metrics"] = [float("nan")]
    path = tmp_path / f"{MARKER}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match=f"^{INVALID}$") as err:
        load_corpus(path)
    _static(err.value, path)


def test_missing_corpus_uses_static_oserror(tmp_path: Path) -> None:
    path = tmp_path / f"{MARKER}.json"
    with pytest.raises(OSError, match=f"^{FILE_UNAVAILABLE}$") as err:
        load_corpus(path)
    _static(err.value, path)


@pytest.mark.parametrize("name", ["out.jsonl", "out.JSONL"])
def test_journal_and_output_collision_is_rejected(tmp_path: Path, name: str) -> None:
    output = tmp_path / name
    with pytest.raises(ValueError, match=f"^{INVALID}$") as err:
        open_journal(output, {"mode": "fixture"})
    assert err.value.__cause__ is None
    assert not output.exists()
    with pytest.raises(ValueError, match=f"^{INVALID}$"):
        write_result(output, {"ok": True})
    assert not output.exists()


def test_existing_output_and_journal_are_exclusive(tmp_path: Path) -> None:
    output = tmp_path / "out.json"
    journal = output.with_suffix(".jsonl")
    output.write_text("{}\n", encoding="utf-8")
    with pytest.raises(OSError, match=f"^{OUTPUT_EXISTS}$"):
        open_journal(output, {"mode": "fixture"})
    assert not journal.exists()
    output.unlink()
    journal.write_text("{}\n", encoding="utf-8")
    with pytest.raises(OSError, match=f"^{OUTPUT_EXISTS}$"):
        open_journal(output, {"mode": "fixture"})
    assert journal.read_text(encoding="utf-8") == "{}\n"
    assert not output.exists()
    fresh = tmp_path / "fresh.json"
    handle = open_journal(fresh, {"mode": "fixture"})
    handle.close()
    with pytest.raises(OSError, match=f"^{OUTPUT_EXISTS}$"):
        open_journal(fresh, {"mode": "other"})
    assert journal.read_text(encoding="utf-8") == "{}\n"
    assert not output.exists()
    fresh.write_text("old\n", encoding="utf-8")
    with pytest.raises(OSError, match=f"^{OUTPUT_EXISTS}$"):
        write_result(fresh, {"ok": True})
    assert fresh.read_text(encoding="utf-8") == "old\n"
    assert journal.read_text(encoding="utf-8") == "{}\n"


def test_symlink_output_and_journal_are_refused(tmp_path: Path) -> None:
    target = tmp_path / "target"
    output = tmp_path / "out.json"
    journal = output.with_suffix(".jsonl")
    output.symlink_to(target)
    with pytest.raises(OSError, match=f"^{OUTPUT_EXISTS}$"):
        open_journal(output, {"mode": "fixture"})
    assert not journal.exists()
    output.unlink()
    journal.symlink_to(target)
    with pytest.raises(OSError, match=f"^{OUTPUT_EXISTS}$"):
        open_journal(output, {"mode": "fixture"})
    assert journal.is_symlink()
    assert not output.exists()
    journal.unlink()
    output.symlink_to(target)
    with pytest.raises(OSError, match=f"^{OUTPUT_EXISTS}$"):
        write_result(output, {"ok": True})


def test_invalid_serialization_does_not_create_final(tmp_path: Path) -> None:
    output = tmp_path / "out.json"
    journal = output.with_suffix(".jsonl")
    handle = open_journal(output, {"mode": "fixture"})
    handle.close()
    with pytest.raises(ValueError, match=f"^{INVALID}$") as err:
        write_result(output, {"v": float("nan")})
    assert err.value.__cause__ is None
    assert not output.exists()
    assert journal.exists()
    assert not _temp(output).exists()


def test_manifest_and_record_flush(tmp_path: Path) -> None:
    output = tmp_path / "out.json"
    journal = output.with_suffix(".jsonl")
    manifest = {"mode": "fixture", "revision": "a" * 40}
    handle = open_journal(output, manifest)
    rows = journal.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    assert json.loads(rows[0]) == manifest
    write_record(handle, {"case_id": "B01", "repeat": 1})
    rows = journal.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2
    assert json.loads(rows[1]) == {"case_id": "B01", "repeat": 1}
    handle.close()


def test_partial_journal_is_preserved_on_exception(tmp_path: Path) -> None:
    output = tmp_path / "out.json"
    journal = output.with_suffix(".jsonl")
    handle = open_journal(output, {"mode": "fixture"})
    write_record(handle, {"case_id": "B01", "repeat": 1})
    with pytest.raises(ValueError, match=f"^{INVALID}$"):
        write_record(handle, {"v": float("nan")})
    handle.close()
    rows = journal.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2
    assert json.loads(rows[0]) == {"mode": "fixture"}
    assert json.loads(rows[1]) == {"case_id": "B01", "repeat": 1}
    assert not output.exists()
    with pytest.raises(ValueError, match=f"^{INVALID}$"):
        write_result(output, {"v": float("nan")})
    assert journal.exists()
    assert not output.exists()


def test_write_result_installs_valid_final(tmp_path: Path) -> None:
    output = tmp_path / "out.json"
    journal = output.with_suffix(".jsonl")
    payload = {"ok": True, "cases": 1}
    handle = open_journal(output, {"mode": "fixture"})
    write_record(handle, {"case_id": "B01", "repeat": 1})
    handle.close()
    write_result(output, payload)
    assert json.loads(output.read_text(encoding="utf-8")) == payload
    rows = journal.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2
    assert json.loads(rows[0]) == {"mode": "fixture"}
    assert json.loads(rows[1]) == {"case_id": "B01", "repeat": 1}
    assert not _temp(output).exists()


@pytest.mark.parametrize("flush", [False, True])
def test_write_result_partial_failure_leaves_no_final(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flush: bool
) -> None:
    output = tmp_path / f"{MARKER}.json"
    journal = output.with_suffix(".jsonl")
    handle = open_journal(output, {"mode": "fixture"})
    handle.close()
    prior = journal.read_text(encoding="utf-8")
    _break_exclusive(monkeypatch, flush=flush)
    with pytest.raises(OSError, match=f"^{FILE_UNAVAILABLE}$") as err:
        write_result(output, {"ok": True})
    _static(err.value, output)
    _static(err.value, journal)
    assert not output.exists()
    assert journal.read_text(encoding="utf-8") == prior
    assert not _temp(output).exists()


def test_write_result_keyboardinterrupt_cleans_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "out.json"
    journal = output.with_suffix(".jsonl")
    handle = open_journal(output, {"mode": "fixture"})
    write_record(handle, {"case_id": "B01", "repeat": 1})
    handle.close()
    prior = journal.read_text(encoding="utf-8")
    _break_exclusive(monkeypatch, flush=False, interrupt=True)
    with pytest.raises(KeyboardInterrupt):
        write_result(output, {"ok": True})
    assert not output.exists()
    assert journal.read_text(encoding="utf-8") == prior
    assert not _temp(output).exists()


def test_write_result_refuses_existing_final_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / f"{MARKER}.json"
    journal = output.with_suffix(".jsonl")
    handle = open_journal(output, {"mode": "fixture"})
    handle.close()
    prior = journal.read_text(encoding="utf-8")
    real_link = os.link

    def raced(source: str | os.PathLike[str], dest: str | os.PathLike[str]) -> None:
        Path(dest).write_text("old\n", encoding="utf-8")
        real_link(source, dest)

    monkeypatch.setattr("app.evaluation_io.os.link", raced)
    with pytest.raises(OSError, match=f"^{OUTPUT_EXISTS}$") as err:
        write_result(output, {"ok": True})
    _static(err.value, output)
    assert output.read_text(encoding="utf-8") == "old\n"
    assert journal.read_text(encoding="utf-8") == prior
    assert not _temp(output).exists()


@pytest.mark.parametrize("flush", [False, True])
def test_manifest_write_failure_preserves_partial_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flush: bool
) -> None:
    output = tmp_path / f"{MARKER}.json"
    journal = output.with_suffix(".jsonl")
    _break_exclusive(monkeypatch, flush=flush)
    with pytest.raises(OSError, match=f"^{FILE_UNAVAILABLE}$") as err:
        open_journal(output, {"mode": "fixture"})
    _static(err.value, journal)
    _static(err.value, output)
    assert journal.exists()
    assert not output.exists()
    with pytest.raises(OSError, match=f"^{OUTPUT_EXISTS}$"):
        open_journal(output, {"mode": "fixture"})
    assert journal.exists()
    assert not output.exists()
