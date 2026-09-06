from __future__ import annotations

import fcntl
import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def lease(git_dir: Path) -> Iterator[Path]:
    os.umask(0o077)
    with (git_dir / "fewia-supervisor.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock.seek(0)
        prior = lock.read().strip()
        if prior:
            status = Path(prior) / "status.json"
            if status.exists():
                pid = json.loads(status.read_text())["pid"]
                try:
                    os.killpg(pid, 0)
                except ProcessLookupError:
                    pass
                else:
                    raise RuntimeError(
                        "Prior writer group exists; inspect and stop it before retrying"
                    )
        state = Path(tempfile.mkdtemp(prefix="fewia-supervisor-"))
        lock.seek(0)
        lock.truncate()
        lock.write(str(state))
        lock.flush()
        yield state
