#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import selectors
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

RECORD = "fewia-publication-approval.json"
LIMIT = 16384
LIFETIME = 3600
BODY_LIMIT = 65536
VIEW_LIMIT = 262144
DEADLINE = time.monotonic() + 3.8
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
BODY_KEYS = KEYS | {
    "repo",
    "pr",
    "body_file",
    "body_sha256",
    "body_identity",
    "remote_body_sha256",
}


class Rejected(Exception):
    pass


def require(condition: bool) -> None:
    if not condition:
        raise Rejected


def remaining(limit: float) -> float:
    duration = min(limit, DEADLINE - time.monotonic())
    require(duration > 0)
    return duration


def git(checkout: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(checkout), *arguments],
        capture_output=True,
        timeout=remaining(3),
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


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def safe_repo(value: str) -> bool:
    return (
        re.fullmatch(r"[A-Za-z0-9_-]+/[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*", value)
        is not None
    )


def body_argv(repo: str, pr: str, path: str) -> list[str]:
    require(safe_repo(repo))
    require(re.fullmatch(r"[1-9][0-9]{0,9}", pr) is not None)
    require(re.fullmatch(r"/(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+", path) is not None)
    require(all(part not in {".", ".."} for part in path.split("/")[1:]))
    return ["gh", "pr", "edit", pr, "--repo", f"github.com/{repo}", "--body-file", path]


def file_identity(info: os.stat_result) -> list[int]:
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def body_snapshot(path: str) -> tuple[str, list[int]]:
    parts = Path(path).parts
    require(Path(path).is_absolute())
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[1:-1]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
            )
            os.close(directory)
            directory = child
        descriptor = os.open(
            parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
        with os.fdopen(descriptor, "rb") as source:
            info = os.fstat(source.fileno())
            require(stat.S_ISREG(info.st_mode))
            require(stat.S_IMODE(info.st_mode) == 0o600)
            require(info.st_uid == os.getuid() and info.st_nlink == 1)
            require(0 <= info.st_size <= BODY_LIMIT)
            raw = source.read(BODY_LIMIT + 1)
            require(len(raw) == info.st_size and len(raw) <= BODY_LIMIT)
            require(b"\0" not in raw)
            raw.decode("utf-8")
            require(file_identity(os.fstat(source.fileno())) == file_identity(info))
            current = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
            require(file_identity(current) == file_identity(info))
            require(canonical_path(path) == Path(path))
            require(file_identity(Path(path).lstat()) == file_identity(info))
            return digest(raw), file_identity(info)
    finally:
        os.close(directory)


def gh_environment() -> dict[str, str]:
    require(os.environ.get("GH_HOST", "") in {"", "github.com"})
    for name in ("GH_REPO", "GH_CONFIG_DIR", "GH_DEBUG", "DEBUG"):
        require(not os.environ.get(name))
    require("GH_PATH" not in os.environ)
    environment = os.environ.copy()
    environment.update(
        GH_PROMPT_DISABLED="1",
        GH_NO_UPDATE_NOTIFIER="1",
        GH_NO_EXTENSION_UPDATE_NOTIFIER="1",
        GH_PAGER="cat",
        PAGER="cat",
    )
    return environment


def view_body(checkout: Path, expected: dict[str, Any]) -> str:
    fields = "number,url,headRefOid,headRefName,isCrossRepository,state,isDraft,body"
    timeout = remaining(1.2)
    process = subprocess.Popen(
        [
            "gh",
            "pr",
            "view",
            expected["pr"],
            "--repo",
            f"github.com/{expected['repo']}",
            "--json",
            fields,
        ],
        cwd=checkout,
        env=gh_environment(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    raw = bytearray()
    deadline = min(DEADLINE, time.monotonic() + timeout)
    try:
        if process.stdout is None:
            raise Rejected
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                duration = deadline - time.monotonic()
                require(duration > 0)
                require(bool(selector.select(duration)))
                chunk = os.read(
                    process.stdout.fileno(), min(8192, VIEW_LIMIT + 1 - len(raw))
                )
                if not chunk:
                    break
                raw.extend(chunk)
                require(len(raw) <= VIEW_LIMIT)
        require(process.wait(timeout=remaining(0.2)) == 0)
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=0.2)
        finally:
            if process.stdout is not None:
                process.stdout.close()
    value = load_object(bytes(raw))
    require(set(value) == set(fields.split(",")))
    require(type(value["number"]) is int and str(value["number"]) == expected["pr"])
    for field in ("url", "headRefOid", "headRefName", "state", "body"):
        require(type(value[field]) is str)
    target = re.fullmatch(
        r"https://github\.com/([A-Za-z0-9_-]+/[A-Za-z0-9_.-]+)/pull/([1-9][0-9]*)",
        value["url"],
    )
    if target is None:
        raise Rejected
    require(target[1].casefold() == expected["repo"].casefold())
    require(target[2] == expected["pr"])
    require(value["headRefOid"] == expected["sha"])
    require(value["headRefName"] == expected["branch"][11:])
    require(value["isCrossRepository"] is False)
    require(value["state"] == "OPEN" and value["isDraft"] is True)
    require("\0" not in value["body"])
    return digest(value["body"].encode("utf-8"))


def body_context(expected: dict[str, Any], record: dict[str, Any]) -> None:
    repo = record["repo"]
    push_repo = re.sub(
        r"^(?:git@github\.com:|https://github\.com/|ssh://git@github\.com/)",
        "",
        expected["push_url"],
    )
    if push_repo.casefold().endswith(".git"):
        push_repo = push_repo[:-4]
    require(repo.casefold() == push_repo.casefold())
    expected.update(
        version=2,
        argv=body_argv(repo, record["pr"], record["body_file"]),
        repo=repo,
        pr=record["pr"],
        body_file=record["body_file"],
    )
    checksum, identity = body_snapshot(record["body_file"])
    require(checksum == record["body_sha256"])
    expected.update(body_sha256=checksum, body_identity=identity)


def validate(record: dict[str, Any], now: int) -> None:
    version = record.get("version")
    require(type(version) is int and version in {1, 2})
    keys = KEYS if version == 1 else BODY_KEYS
    require(set(record) == keys)
    for key in keys - {"version", "argv", "issued", "expires", "body_identity"}:
        require(type(record[key]) is str)
    require(type(record["argv"]) is list)
    require(all(type(item) is str for item in record["argv"]))
    require(type(record["issued"]) is int and type(record["expires"]) is int)
    require(0 <= record["issued"] <= now < record["expires"])
    require(0 < record["expires"] - record["issued"] <= LIFETIME)
    require(bool(record["source"].strip()) and bool(record["reason"].strip()))
    if version == 2:
        argv = body_argv(record["repo"], record["pr"], record["body_file"])
        require(record["argv"] == argv)
        for key in ("body_sha256", "remote_body_sha256"):
            require(re.fullmatch(r"[0-9a-f]{64}", record[key]) is not None)
        identity = record["body_identity"]
        require(type(identity) is list and len(identity) == 5)
        require(all(type(item) is int and item >= 0 for item in identity))


def record_approval(arguments: argparse.Namespace) -> None:
    checkout = canonical_path(arguments.checkout)
    expected = context(checkout, arguments.remote)
    require(expected["push_url"] == arguments.push_url)
    require(safe_branch(arguments.branch))
    require(expected["branch"] == f"refs/heads/{arguments.branch}")
    require(re.fullmatch(r"[0-9a-f]{40}", arguments.head) is not None)
    require(expected["sha"] == arguments.head)
    require(bool(arguments.source.strip()) and bool(arguments.reason.strip()))
    if arguments.action == "record-pr-body":
        require(re.fullmatch(r"[0-9a-f]{64}", arguments.remote_body_sha256) is not None)
        reviewed = {
            "repo": arguments.repo,
            "pr": arguments.pr,
            "body_file": arguments.body_file,
            "body_sha256": arguments.body_sha256,
        }
        body_context(expected, reviewed)
        require(view_body(checkout, expected) == arguments.remote_body_sha256)
        expected["remote_body_sha256"] = arguments.remote_body_sha256
        require(
            body_snapshot(arguments.body_file)
            == (expected["body_sha256"], expected["body_identity"])
        )
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
            if record["version"] == 2:
                require(command == " ".join(record["argv"]))
            expected = context(checkout, record["remote"])
            if record["version"] == 2:
                body_context(expected, record)
            require(all(record[key] == value for key, value in expected.items()))
            require(command == " ".join(expected["argv"]))
            if record["version"] == 2:
                require(view_body(checkout, expected) == record["remote_body_sha256"])
                fresh = context(checkout, record["remote"])
                require(
                    all(
                        record[key] == value
                        for key, value in fresh.items()
                        if key not in {"version", "argv"}
                    )
                )
                require(
                    body_snapshot(record["body_file"])
                    == (record["body_sha256"], record["body_identity"])
                )
            current = os.stat(RECORD, dir_fd=directory, follow_symlinks=False)
            require(file_identity(current) == file_identity(info))
            require(file_identity(os.fstat(source.fileno())) == file_identity(info))
            validate(record, int(time.time()))
            os.unlink(RECORD, dir_fd=directory)
    finally:
        os.close(directory)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record one approved publication command."
    )
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("record", "record-pr-body"):
        record = commands.add_parser(action)
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
        if action == "record-pr-body":
            for name in (
                "repo",
                "pr",
                "body-file",
                "body-sha256",
                "remote-body-sha256",
            ):
                record.add_argument(f"--{name}", required=True)
    commands.add_parser("consume")
    arguments = parser.parse_args()
    try:
        if arguments.action in {"record", "record-pr-body"}:
            record_approval(arguments)
        else:
            consume_approval()
    except (Rejected, OSError, ValueError, RecursionError, subprocess.SubprocessError):
        print("Publication approval unavailable or does not match.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
