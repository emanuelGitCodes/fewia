import os
import traceback
from pathlib import Path
from typing import cast

import pytest

from app import evaluation_io_json
from app.evaluation_io_json import canonical_json_bytes, load_json


def test_canonical_json_bytes_is_deterministic() -> None:
    first = {"z": [None, True, 12, 1.5], "a": {"b": "é", "a": False}}
    second = {"a": {"a": False, "b": "é"}, "z": [None, True, 12, 1.5]}
    expected = b'{"a":{"a":false,"b":"\\u00e9"},"z":[null,true,12,1.5]}'
    assert canonical_json_bytes(first) == canonical_json_bytes(second) == expected


@pytest.mark.parametrize("value", [None, [], "private-payload", 1, True])
def test_canonical_json_bytes_rejects_non_object_roots(value: object) -> None:
    with pytest.raises(ValueError, match="^evaluation JSON is invalid$"):
        canonical_json_bytes(value)


@pytest.mark.parametrize(
    "value",
    [
        {1: "private-payload"},
        {"a": {False: "private-payload"}},
        {"a": float("nan")},
        {"a": [float("inf")]},
        {"a": float("-inf")},
        {"a": (1, 2)},
        {"a": {1, 2}},
        {"a": b"private-payload"},
        {"a": object()},
        {"reasoningContent": "private-payload"},
        {"a": [{"reasoningContent": "private-payload"}]},
    ],
)
def test_canonical_json_bytes_rejects_invalid_values(value: object) -> None:
    with pytest.raises(ValueError, match="^evaluation JSON is invalid$") as error:
        canonical_json_bytes(value)
    assert "private-payload" not in "".join(traceback.format_exception(error.value))


def test_canonical_json_bytes_rejects_cycles() -> None:
    report: dict[str, object] = {}
    report["self"] = report
    items: list[object] = []
    items.append(items)
    for value in (report, {"items": items}):
        with pytest.raises(ValueError, match="^evaluation JSON is invalid$"):
            canonical_json_bytes(value)


def test_canonical_json_bytes_accepts_shared_values() -> None:
    child: dict[str, object] = {"ok": True}
    expected = b'{"a":{"ok":true},"b":{"ok":true}}'
    assert canonical_json_bytes({"a": child, "b": child}) == expected


def test_canonical_json_bytes_rejects_excessive_recursion() -> None:
    root: dict[str, object] = {}
    cursor = root
    for _ in range(10_000):
        child: dict[str, object] = {}
        cursor["next"] = child
        cursor = child
    with pytest.raises(ValueError, match="^evaluation JSON is invalid$"):
        canonical_json_bytes(root)


def test_load_json_returns_independent_data(tmp_path: Path) -> None:
    path = tmp_path / "input.json"
    raw = '{"é":{"items":[1,true,null]},"count":2}'.encode()
    path.write_bytes(raw)
    first = load_json(path, max_bytes=len(raw))
    nested = cast(dict[str, object], first["é"])
    cast(list[object], nested["items"]).append("changed")
    assert load_json(path) == {"é": {"items": [1, True, None]}, "count": 2}
    assert path.read_bytes() == raw


@pytest.mark.parametrize(
    "raw",
    [
        b"null",
        b"[]",
        b'"private-payload"',
        b"42",
        b'{"a":1,"a":2}',
        b'{"nested":{"a":1,"a":2}}',
        b'{"a":1,"\\u0061":2}',
        b'{"a":NaN}',
        b'{"a":Infinity}',
        b'{"a":-Infinity}',
        b'{"a":1e9999}',
        b'{"reasoningContent":"private-payload"}',
        b'{"a":[{"reasoningContent":"private-payload"}]}',
        b'{"private-payload":',
        b'{"a":1} trailing-private-payload',
        b'{"a":"\xff"}',
        b"",
        b'{"a":' + b"[" * 10_000 + b"]" * 10_000 + b"}",
    ],
)
def test_load_json_rejects_invalid_input(tmp_path: Path, raw: bytes) -> None:
    path = tmp_path / "private-path.json"
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="^evaluation JSON is invalid$") as error:
        load_json(path)
    rendered = "".join(traceback.format_exception(error.value))
    assert "private-payload" not in rendered
    assert "private-path" not in rendered
    assert str(tmp_path) not in rendered


@pytest.mark.parametrize("limit", [0, -1, True, False, 1.0, "8", None])
def test_load_json_requires_positive_exact_integer_limit(
    tmp_path: Path, limit: object
) -> None:
    with pytest.raises(ValueError, match="^evaluation JSON is invalid$"):
        load_json(tmp_path / "missing.json", max_bytes=cast(int, limit))


@pytest.mark.parametrize("kind", ["symlink", "directory", "missing", "fifo"])
def test_load_json_rejects_unavailable_paths(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "private-path"
    if kind == "symlink":
        target = tmp_path / "target.json"
        target.write_text("{}", encoding="utf-8")
        path.symlink_to(target)
    elif kind == "directory":
        path.mkdir()
    elif kind == "fifo":
        os.mkfifo(path)
    with pytest.raises(OSError, match="^evaluation files are unavailable$") as error:
        load_json(path)
    rendered = "".join(traceback.format_exception(error.value))
    assert "private-path" not in rendered
    assert str(tmp_path) not in rendered


def test_load_json_rejects_oversized_file_before_read_or_decode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "input.json"
    path.write_bytes(b'{"private-payload":true}')

    def unexpected(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("oversized input reached read or decode")

    monkeypatch.setattr(evaluation_io_json.os, "read", unexpected)
    monkeypatch.setattr(evaluation_io_json.json, "loads", unexpected)
    with pytest.raises(ValueError, match="^evaluation JSON is invalid$"):
        load_json(path, max_bytes=2)


def test_load_json_bounds_reads_when_file_grows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "input.json"
    path.write_bytes(b'{"private-payload":true}')
    real_fstat = os.fstat
    real_read = os.read
    requests: list[int] = []

    def smaller_stat(fd: int) -> os.stat_result:
        fields = list(real_fstat(fd))
        fields[6] = 0
        return os.stat_result(fields)

    def short_read(fd: int, size: int) -> bytes:
        requests.append(size)
        return real_read(fd, min(size, 3))

    monkeypatch.setattr(evaluation_io_json.os, "fstat", smaller_stat)
    monkeypatch.setattr(evaluation_io_json.os, "read", short_read)
    with pytest.raises(ValueError, match="^evaluation JSON is invalid$"):
        load_json(path, max_bytes=8)
    assert requests == [9, 6, 3]


def test_load_json_opens_without_following_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "input.json"
    path.write_text("{}", encoding="utf-8")
    real_open = os.open
    flags_seen: list[int] = []

    def checked_open(file: Path, flags: int) -> int:
        flags_seen.append(flags)
        return real_open(file, flags)

    monkeypatch.setattr(evaluation_io_json.os, "open", checked_open)
    assert load_json(path) == {}
    assert len(flags_seen) == 1
    assert flags_seen[0] & os.O_NOFOLLOW
    assert flags_seen[0] & os.O_NONBLOCK


def test_load_json_closes_descriptor_after_invalid_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "input.json"
    path.write_text("[]", encoding="utf-8")
    real_close = os.close
    closed: list[int] = []

    def tracked_close(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    monkeypatch.setattr(evaluation_io_json.os, "close", tracked_close)
    with pytest.raises(ValueError, match="^evaluation JSON is invalid$"):
        load_json(path)
    assert len(closed) == 1


def test_load_json_sanitizes_read_failures_and_closes_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "input.json"
    path.write_text("{}", encoding="utf-8")
    real_close = os.close
    closed: list[int] = []

    def failed_read(_fd: int, _size: int) -> bytes:
        raise OSError("private-path private-payload")

    def tracked_close(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    monkeypatch.setattr(evaluation_io_json.os, "read", failed_read)
    monkeypatch.setattr(evaluation_io_json.os, "close", tracked_close)
    with pytest.raises(OSError, match="^evaluation files are unavailable$") as error:
        load_json(path)
    rendered = "".join(traceback.format_exception(error.value))
    assert "private-path" not in rendered
    assert "private-payload" not in rendered
    assert len(closed) == 1
