import hashlib
import io
from pathlib import Path
from typing import BinaryIO, cast

import pytest

from app import evaluation_io
from app.evaluation_io import EvaluationOutput
from app.evaluation_io_json import canonical_json_bytes, load_json


def test_load_json_is_reexported() -> None:
    assert evaluation_io.load_json is load_json


@pytest.mark.parametrize("kind", ["directory", "file", "symlink", "dangling"])
def test_existing_run_path_is_refused(tmp_path: Path, kind: str) -> None:
    directory = tmp_path / "run"
    target = tmp_path / "target"
    if kind == "directory":
        directory.mkdir()
    elif kind == "file":
        directory.write_bytes(b"existing")
    else:
        if kind == "symlink":
            target.mkdir()
        directory.symlink_to(target)
    with pytest.raises(OSError, match="^evaluation output already exists$"):
        with EvaluationOutput(directory):
            pytest.fail("existing path was accepted")
    assert directory.exists() or directory.is_symlink()
    if kind == "file":
        assert directory.read_bytes() == b"existing"


@pytest.mark.parametrize("symlink", [False, True])
def test_journal_creation_is_exclusive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, symlink: bool
) -> None:
    directory = tmp_path / "run"
    target = tmp_path / "target"
    target.write_bytes(b"existing")
    original_mkdir = Path.mkdir

    def create_with_journal(path: Path) -> None:
        original_mkdir(path)
        journal = path / "slots.jsonl"
        if symlink:
            journal.symlink_to(target)
        else:
            journal.write_bytes(b"existing")

    monkeypatch.setattr(Path, "mkdir", create_with_journal)
    with pytest.raises(OSError, match="^evaluation output already exists$"):
        with EvaluationOutput(directory):
            pytest.fail("existing journal was accepted")
    assert target.read_bytes() == b"existing"
    assert (directory / "slots.jsonl").read_bytes() == b"existing"


@pytest.mark.parametrize(
    "name", ["report.json", "report.md", "completion.pending", "completion.json"]
)
@pytest.mark.parametrize("symlink", [False, True])
def test_final_paths_are_exclusive(tmp_path: Path, name: str, symlink: bool) -> None:
    directory = tmp_path / "run"
    target = tmp_path / "existing"
    target.write_bytes(b"existing")
    with EvaluationOutput(directory) as output:
        output.append_slot({"slot": 1})
        path = directory / name
        if symlink:
            path.symlink_to(target)
        else:
            path.write_bytes(b"existing")
        with pytest.raises(OSError, match="^evaluation output already exists$"):
            output.finish({"finished": True}, "report")
        assert path.read_bytes() == b"existing"
        assert target.read_bytes() == b"existing"
        assert output._journal is None
    if name != "completion.json":
        assert not (directory / "completion.json").exists()
    assert (directory / "slots.jsonl").read_bytes() == b'{"slot":1}\n'


@pytest.mark.parametrize(
    "payload",
    [
        {"value": float("nan")},
        {"value": float("inf")},
        {"value": float("-inf")},
        {"value": object()},
        {"value": (1, 2)},
        {1: "invalid key"},
        {"nested": [{"reasoningContent": "private"}]},
        {"reasoningContent": None},
        [],
    ],
)
@pytest.mark.parametrize("operation", ["slot", "report"])
def test_invalid_json_is_rejected_without_a_marker(
    tmp_path: Path, payload: object, operation: str
) -> None:
    directory = tmp_path / "run"
    with EvaluationOutput(directory) as output:
        output.append_slot({"prior": True})
        handle = output._journal
        with pytest.raises(ValueError, match="^evaluation JSON is invalid$"):
            if operation == "slot":
                output.append_slot(cast(dict[str, object], payload))
            else:
                output.finish(cast(dict[str, object], payload), "report")
        assert handle is not None and handle.closed
    assert (directory / "slots.jsonl").read_bytes() == b'{"prior":true}\n'
    assert not (directory / "completion.json").exists()
    assert not (directory / "report.json").exists()


@pytest.mark.parametrize("container", ["list", "dict"])
@pytest.mark.parametrize("operation", ["slot", "report"])
def test_cycles_are_rejected(tmp_path: Path, container: str, operation: str) -> None:
    payload: dict[str, object] = {}
    if container == "list":
        children: list[object] = []
        children.append(children)
        payload["value"] = children
    else:
        payload["value"] = payload
    with EvaluationOutput(tmp_path / "run") as output:
        with pytest.raises(ValueError, match="^evaluation JSON is invalid$"):
            if operation == "slot":
                output.append_slot(payload)
            else:
                output.finish(payload, "report")
        assert output._journal is None


def test_slot_is_canonical_copied_and_synced_before_return(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "run"
    snapshots: list[bytes] = []
    real_fsync = evaluation_io.os.fsync

    def capture_fsync(fd: int) -> None:
        snapshots.append((directory / "slots.jsonl").read_bytes())
        real_fsync(fd)

    monkeypatch.setattr(evaluation_io.os, "fsync", capture_fsync)
    child: dict[str, object] = {"b": "é", "a": [1, True, None]}
    slot: dict[str, object] = {"z": child, "a": 1.25}
    expected = b'{"a":1.25,"z":{"a":[1,true,null],"b":"\\u00e9"}}\n'
    with EvaluationOutput(directory) as output:
        output.append_slot(slot)
        assert snapshots == [expected]
        child["b"] = "changed"
        slot.clear()
        assert (directory / "slots.jsonl").read_bytes() == expected


def test_emit_completes_short_writes_and_flushes_before_fsync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class ShortWriter(io.BytesIO):
        def write(self, data: bytes | bytearray | memoryview) -> int:
            events.append("write")
            return super().write(data[:3])

        def flush(self) -> None:
            events.append("flush")
            super().flush()

        def fileno(self) -> int:
            return 7

    def synced(fd: int) -> None:
        assert fd == 7
        events.append("fsync")

    monkeypatch.setattr(evaluation_io.os, "fsync", synced)
    handle = ShortWriter()
    evaluation_io._emit(cast(BinaryIO, handle), b'{"value":1}\n')
    assert handle.getvalue() == b'{"value":1}\n'
    assert events[-2:] == ["flush", "fsync"]
    assert events.count("write") > 1


@pytest.mark.parametrize("interrupted", [False, True])
def test_failed_append_preserves_complete_lines_and_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interrupted: bool
) -> None:
    directory = tmp_path / "run"
    with EvaluationOutput(directory) as output:
        output.append_slot({"prior": 1})
        handle = output._journal

        def fail_write(handle: BinaryIO, data: bytes) -> None:
            handle.write(data[:5])
            if interrupted:
                raise KeyboardInterrupt
            raise OSError("sensitive payload and path")

        monkeypatch.setattr(evaluation_io, "_emit", fail_write)
        error_type = KeyboardInterrupt if interrupted else OSError
        with pytest.raises(error_type) as caught:
            output.append_slot({"next": 2})
        if not interrupted:
            assert str(caught.value) == "evaluation files are unavailable"
            assert caught.value.__suppress_context__
        assert handle is not None and handle.closed
        with pytest.raises(OSError, match="^evaluation files are unavailable$"):
            output.finish({}, "report")
    assert (directory / "slots.jsonl").read_bytes() == b'{"prior":1}\n'
    assert not (directory / "completion.json").exists()


def test_context_interruption_retains_journal_and_closes(tmp_path: Path) -> None:
    directory = tmp_path / "run"
    handle: BinaryIO | None = None
    with pytest.raises(KeyboardInterrupt):
        with EvaluationOutput(directory) as output:
            handle = output._journal
            output.append_slot({"prior": 1})
            raise KeyboardInterrupt
    assert handle is not None and handle.closed
    assert (directory / "slots.jsonl").read_bytes() == b'{"prior":1}\n'
    assert not (directory / "completion.json").exists()


@pytest.mark.parametrize(
    "failed_file", ["report.json", "report.md", "completion.pending"]
)
@pytest.mark.parametrize("interrupted", [False, True])
def test_failed_finish_keeps_evidence_without_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failed_file: str,
    interrupted: bool,
) -> None:
    directory = tmp_path / "run"
    handles: list[BinaryIO] = []
    real_emit = evaluation_io._emit
    with EvaluationOutput(directory) as output:
        output.append_slot({"prior": 1})
        assert output._journal is not None
        handles.append(output._journal)

        def fail_emit(handle: BinaryIO, data: bytes) -> None:
            handles.append(handle)
            if Path(handle.name).name == failed_file:
                handle.write(data[:5])
                if interrupted:
                    raise KeyboardInterrupt
                raise OSError("sensitive report text and path")
            real_emit(handle, data)

        monkeypatch.setattr(evaluation_io, "_emit", fail_emit)
        error_type = KeyboardInterrupt if interrupted else OSError
        with pytest.raises(error_type) as caught:
            output.finish({"report": "sensitive"}, "sensitive markdown")
        if not interrupted:
            assert str(caught.value) == "evaluation files are unavailable"
        assert all(handle.closed for handle in handles)
    assert (directory / "slots.jsonl").read_bytes() == b'{"prior":1}\n'
    assert (directory / failed_file).exists()
    assert not (directory / "completion.json").exists()


@pytest.mark.parametrize("operation", ["slot", "report"])
def test_fsync_failure_closes_journal_without_a_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    directory = tmp_path / "run"
    with EvaluationOutput(directory) as output:
        output.append_slot({"prior": 1})
        handle = output._journal

        def fail_fsync(fd: int) -> None:
            raise OSError("sensitive fsync failure")

        monkeypatch.setattr(evaluation_io.os, "fsync", fail_fsync)
        with pytest.raises(OSError, match="^evaluation files are unavailable$"):
            if operation == "slot":
                output.append_slot({"next": 2})
            else:
                output.finish({}, "report")
        assert handle is not None and handle.closed
    assert (directory / "slots.jsonl").read_bytes() == b'{"prior":1}\n'
    assert not (directory / "completion.json").exists()


def test_completion_link_failure_preserves_final_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "run"

    def fail_link(src: Path, dst: Path, *, follow_symlinks: bool) -> None:
        assert not follow_symlinks
        assert src.name == "completion.pending"
        assert dst.name == "completion.json"
        assert (directory / "report.json").read_bytes() == b'{"done":true}'
        assert (directory / "report.md").read_bytes() == b"report"
        raise OSError("sensitive publication failure")

    monkeypatch.setattr(evaluation_io.os, "link", fail_link)
    with EvaluationOutput(directory) as output:
        output.append_slot({"prior": 1})
        handle = output._journal
        with pytest.raises(OSError, match="^evaluation files are unavailable$"):
            output.finish({"done": True}, "report")
        assert handle is not None and handle.closed
    assert (directory / "slots.jsonl").read_bytes() == b'{"prior":1}\n'
    assert load_json(directory / "completion.pending")["slot_count"] == 1
    assert not (directory / "completion.json").exists()


@pytest.mark.parametrize(
    "failed_file", ["slots.jsonl", "report.json", "report.md", "completion.pending"]
)
def test_close_failure_is_redacted_and_prevents_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failed_file: str
) -> None:
    directory = tmp_path / "run"
    handles: list[BinaryIO] = []
    original_open = Path.open

    class CloseFailure(io.FileIO):
        def close(self) -> None:
            if not self.closed:
                super().close()
                raise OSError("sensitive close failure")

    def open_with_close_failure(
        path: Path, mode: str = "r", *, buffering: int = -1
    ) -> BinaryIO:
        if mode == "x+b" and path.name == failed_file:
            handle = cast(BinaryIO, CloseFailure(path, mode))
        else:
            handle = original_open(path, mode, buffering=buffering)
        handles.append(handle)
        return handle

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", open_with_close_failure)
        with EvaluationOutput(directory) as output:
            output.append_slot({"prior": 1})
            with pytest.raises(OSError, match="^evaluation files are unavailable$"):
                output.finish({"done": True}, "report")
            assert all(handle.closed for handle in handles)
    assert (directory / "slots.jsonl").read_bytes() == b'{"prior":1}\n'
    assert not (directory / "completion.json").exists()


def test_normal_exit_fsync_failure_closes_and_redacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "run"
    handle: BinaryIO | None = None

    def fail_fsync(fd: int) -> None:
        raise OSError("sensitive exit failure")

    with pytest.raises(OSError, match="^evaluation files are unavailable$"):
        with EvaluationOutput(directory) as output:
            handle = output._journal
            output.append_slot({"prior": 1})
            monkeypatch.setattr(evaluation_io.os, "fsync", fail_fsync)
    assert handle is not None and handle.closed
    assert (directory / "slots.jsonl").read_bytes() == b'{"prior":1}\n'
    assert not (directory / "completion.json").exists()


def test_completion_has_actual_hashes_and_journal_count(tmp_path: Path) -> None:
    directory = tmp_path / "run"
    with EvaluationOutput(directory) as output:
        output.append_slot({"slot": 1})
        with (directory / "slots.jsonl").open("ab") as external:
            external.write(canonical_json_bytes({"slot": 2}) + b"\n")
        handle = output._journal
        paths = output.finish({"z": 2, "a": 1}, "# Report\nÉvidence\n")
        assert handle is not None and handle.closed
        assert paths == (
            directory / "report.json",
            directory / "report.md",
            directory / "completion.json",
        )
        assert paths.report.read_bytes() == b'{"a":1,"z":2}'
        assert paths.markdown.read_text(encoding="utf-8") == "# Report\nÉvidence\n"
        marker = load_json(paths.completion)
        assert marker == {
            "slot_count": 2,
            "sha256": {
                "report.json": hashlib.sha256(paths.report.read_bytes()).hexdigest(),
                "report.md": hashlib.sha256(paths.markdown.read_bytes()).hexdigest(),
            },
        }
        assert paths.completion.read_bytes() == canonical_json_bytes(marker)
        pending = directory / "completion.pending"
        assert pending.read_bytes() == paths.completion.read_bytes()
        with pytest.raises(OSError, match="^evaluation files are unavailable$"):
            output.finish({}, "again")


def test_empty_run_finishes_with_zero_slots(tmp_path: Path) -> None:
    with EvaluationOutput(tmp_path / "run") as output:
        paths = output.finish({}, "")
    assert load_json(paths.completion)["slot_count"] == 0


def test_no_resume_or_writes_outside_context(tmp_path: Path) -> None:
    directory = tmp_path / "run"
    output = EvaluationOutput(directory)
    with pytest.raises(OSError, match="^evaluation files are unavailable$"):
        output.append_slot({})
    with pytest.raises(OSError, match="^evaluation files are unavailable$"):
        output.finish({}, "")
    with output:
        handle = output._journal
        output.append_slot({"prior": 1})
    assert handle is not None and handle.closed
    with pytest.raises(OSError, match="^evaluation output already exists$"):
        output.__enter__()
    with pytest.raises(OSError, match="^evaluation output already exists$"):
        EvaluationOutput(directory).__enter__()
    with pytest.raises(OSError, match="^evaluation files are unavailable$"):
        output.append_slot({})


def test_directory_failure_is_redacted(tmp_path: Path) -> None:
    with pytest.raises(OSError) as caught:
        EvaluationOutput(tmp_path / "sensitive missing parent" / "run").__enter__()
    assert str(caught.value) == "evaluation files are unavailable"
    assert caught.value.__suppress_context__
