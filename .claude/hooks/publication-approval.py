#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

RECORD = "fewia-publication-approval.json"
LIMIT = 16384
LIFETIME = 3600
KEYS = {
    "version",
    "argv",
    "checkout",
    "sha",
    "branch",
    "remote",
    "push_url",
    "config_digest",
    "issued",
    "expires",
    "source",
    "reason",
}


class Rejected(Exception):
    pass


def require(condition: bool) -> None:
    if not condition:
        raise Rejected


def git(checkout: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(checkout), *arguments],
        capture_output=True,
        timeout=3,
        check=False,
    )
    require(result.returncode == 0)
    return result.stdout


def git_text(checkout: Path, *arguments: str) -> str:
    return git(checkout, *arguments).decode("utf-8").rstrip("\n")


def canonical_path(value: str) -> Path:
    path = Path(value)
    require(path.is_absolute() and str(path.resolve(strict=True)) == value)
    return path


def safe_remote(value: str) -> bool:
    return re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", value) is not None


def safe_branch(value: str) -> bool:
    return (
        re.fullmatch(
            r"codex/[A-Za-z0-9][A-Za-z0-9_-]*(?:/[A-Za-z0-9][A-Za-z0-9_-]*)*",
            value,
        )
        is not None
    )


def safe_url(value: str) -> bool:
    return (
        re.fullmatch(
            r"(?:git@github\.com:|https://github\.com/|ssh://git@github\.com/)"
            r"[A-Za-z0-9_-]+/[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*",
            value,
        )
        is not None
    )


def safe_environment() -> None:
    require(
        not any(name.startswith("GIT_") and name != "GIT_PAGER" for name in os.environ)
    )


def context(checkout: Path, remote: str) -> dict[str, Any]:
    safe_environment()
    require(safe_remote(remote))
    require(git_text(checkout, "rev-parse", "--show-toplevel") == str(checkout))
    branch = git_text(checkout, "symbolic-ref", "--quiet", "HEAD")
    require(branch.startswith("refs/heads/") and safe_branch(branch[11:]))
    sha = git_text(checkout, "rev-parse", "--verify", "HEAD")
    require(re.fullmatch(r"[0-9a-f]{40}", sha) is not None)
    urls = git_text(
        checkout, "remote", "get-url", "--push", "--all", remote
    ).splitlines()
    require(len(urls) == 1 and safe_url(urls[0]))
    config = git(checkout, "config", "--null", "--list", "--includes")
    forbidden = {
        b"core.sshcommand",
        b"push.pushoption",
        f"remote.{remote}.pushoption".encode(),
        f"remote.{remote}.receivepack".encode(),
        f"remote.{remote}.vcs".encode(),
    }
    for entry in config.split(b"\0"):
        key, _, value = entry.partition(b"\n")
        require(key not in forbidden)
        if key == f"remote.{remote}.mirror".encode():
            require(value.lower() in {b"false", b"no", b"off", b"0"})
    config_digest = hashlib.sha256(config).hexdigest()
    argv = [
        "git",
        "push",
        "--no-follow-tags",
        "--recurse-submodules=no",
        remote,
        f"{sha}:{branch}",
    ]
    return {
        "version": 1,
        "argv": argv,
        "checkout": str(checkout),
        "sha": sha,
        "branch": branch,
        "remote": remote,
        "push_url": urls[0],
        "config_digest": config_digest,
    }


def metadata(checkout: Path) -> int:
    directory = canonical_path(git_text(checkout, "rev-parse", "--absolute-git-dir"))
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    info = os.fstat(descriptor)
    if info.st_uid != os.getuid():
        os.close(descriptor)
        raise Rejected
    return descriptor


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def load_object(raw: bytes) -> dict[str, Any]:
    value: object = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(value, dict):
        raise Rejected
    return {key: item for key, item in value.items()}


def validate(record: dict[str, Any], now: int) -> None:
    require(set(record) == KEYS)
    require(type(record["version"]) is int and record["version"] == 1)
    for key in KEYS - {"version", "argv", "issued", "expires"}:
        require(type(record[key]) is str)
    require(type(record["argv"]) is list)
    require(all(type(item) is str for item in record["argv"]))
    require(type(record["issued"]) is int and type(record["expires"]) is int)
    require(0 <= record["issued"] <= now < record["expires"])
    require(0 < record["expires"] - record["issued"] <= LIFETIME)
    require(bool(record["source"].strip()) and bool(record["reason"].strip()))


def record_approval(arguments: argparse.Namespace) -> None:
    checkout = canonical_path(arguments.checkout)
    expected = context(checkout, arguments.remote)
    require(expected["push_url"] == arguments.push_url)
    require(safe_branch(arguments.branch))
    require(expected["branch"] == f"refs/heads/{arguments.branch}")
    require(re.fullmatch(r"[0-9a-f]{40}", arguments.head) is not None)
    require(expected["sha"] == arguments.head)
    require(bool(arguments.source.strip()) and bool(arguments.reason.strip()))
    now = int(time.time())
    expected.update(
        issued=now,
        expires=now + LIFETIME,
        source=arguments.source,
        reason=arguments.reason,
    )
    data = (json.dumps(expected, sort_keys=True) + "\n").encode("utf-8")
    require(len(data) <= LIMIT)
    directory = metadata(checkout)
    try:
        descriptor = os.open(
            RECORD,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory,
        )
        with os.fdopen(descriptor, "wb") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
    finally:
        os.close(directory)
    print(" ".join(expected["argv"]))


def consume_approval() -> None:
    require(os.environ.get("FEWIA_HOOK_HOST") == "codex")
    raw = sys.stdin.buffer.read(1048577)
    require(len(raw) <= 1048576)
    payload = load_object(raw)
    tool: object = payload.get("tool_input")
    if not isinstance(tool, dict):
        raise Rejected
    command = tool.get("command")
    if not isinstance(command, str):
        raise Rejected
    project = os.environ.get("CLAUDE_PROJECT_DIR", "")
    checkout = canonical_path(project)
    locations: list[object] = []
    if "cwd" in payload:
        locations.append(payload["cwd"])
    if "workdir" in tool:
        locations.append(tool["workdir"])
    for location in locations or [os.getcwd()]:
        if not isinstance(location, str):
            raise Rejected
        require(canonical_path(location) == checkout)
    # Derive metadata only after the checkout matches the wrapper's project root.
    safe_environment()
    require(git_text(checkout, "rev-parse", "--show-toplevel") == str(checkout))
    directory = metadata(checkout)
    try:
        descriptor = os.open(
            RECORD,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=directory,
        )
        with os.fdopen(descriptor, "rb") as source:
            fcntl.flock(source, fcntl.LOCK_EX | fcntl.LOCK_NB)
            info = os.fstat(source.fileno())
            require(stat.S_ISREG(info.st_mode))
            require(stat.S_IMODE(info.st_mode) == 0o600)
            require(info.st_uid == os.getuid() and info.st_nlink == 1)
            require(0 < info.st_size <= LIMIT)
            raw_record = source.read(LIMIT + 1)
            require(len(raw_record) <= LIMIT)
            record = load_object(raw_record)
            validate(record, int(time.time()))
            expected = context(checkout, record["remote"])
            require(all(record[key] == value for key, value in expected.items()))
            require(command == " ".join(expected["argv"]))
            current = os.stat(RECORD, dir_fd=directory, follow_symlinks=False)
            require((current.st_dev, current.st_ino) == (info.st_dev, info.st_ino))
            validate(record, int(time.time()))
            os.unlink(RECORD, dir_fd=directory)
    finally:
        os.close(directory)


def main() -> int:
    parser = argparse.ArgumentParser(description="Record one separately approved push.")
    commands = parser.add_subparsers(dest="action", required=True)
    record = commands.add_parser("record")
    for name in (
        "checkout",
        "remote",
        "push-url",
        "branch",
        "head",
        "source",
        "reason",
    ):
        record.add_argument(f"--{name}", required=True)
    commands.add_parser("consume")
    arguments = parser.parse_args()
    try:
        if arguments.action == "record":
            record_approval(arguments)
        else:
            consume_approval()
    except (Rejected, OSError, ValueError, subprocess.SubprocessError):
        print("Publication approval unavailable or does not match.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
