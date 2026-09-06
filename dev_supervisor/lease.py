from __future__ import annotations

import fcntl
import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def occupied(status: Path) -> bool:
    try:
        data: Any = json.loads(status.read_text())
    except (OSError, ValueError, TypeError):
        return True
    if not isinstance(data, dict) or data.get("state") != "stopped":
        pid = data.get("pid") if isinstance(data, dict) else None
        if not isinstance(pid, int) or pid <= 0:
            return True
        try:
            os.killpg(pid, 0)
        except ProcessLookupError:
            return False
        except OSError:
            return True
        return True
    return False


@contextmanager
def lease(git_dir: Path, worktree: Path | None = None) -> Iterator[Path]:
    root = git_dir if worktree is None else worktree
    os.umask(0o077)
    with (git_dir / "fewia-supervisor.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock.seek(0)
        prior = lock.read().strip()
        if prior:
            status = Path(prior) / "status.json"
            if not status.exists() or occupied(status):
                raise RuntimeError(
                    "Prior writer group exists; inspect and stop it before retrying"
                )
        state = Path(tempfile.mkdtemp(prefix=".fewia-supervisor-", dir=root))
        os.chmod(state, 0o700)
        lock.seek(0)
        lock.truncate()
        lock.write(str(state))
        lock.flush()
        yield state
