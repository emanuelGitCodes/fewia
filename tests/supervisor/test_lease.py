import json
import os
from pathlib import Path

import pytest

from dev_supervisor.lease import lease


def test_lease_refuses_second_owner(tmp_path: Path) -> None:
    with lease(tmp_path) as state:
        assert state.stat().st_mode & 0o077 == 0
        with pytest.raises(BlockingIOError), lease(tmp_path):
            pass


def test_orphan_group_blocks_new_writer(tmp_path: Path) -> None:
    state = tmp_path / "old"
    state.mkdir()
    (state / "status.json").write_text(json.dumps({"pid": os.getpgrp()}))
    (tmp_path / "fewia-supervisor.lock").write_text(str(state))
    with pytest.raises(RuntimeError, match="Prior writer"), lease(tmp_path):
        pass


def _lock(tmp_path: Path, payload: dict[str, object] | None) -> None:
    state = tmp_path / "old"
    state.mkdir()
    if payload is not None:
        (state / "status.json").write_text(json.dumps(payload))
    (tmp_path / "fewia-supervisor.lock").write_text(str(state))


def test_stopped_status_allows_new_lease(tmp_path: Path) -> None:
    _lock(tmp_path, {"state": "stopped", "pid": os.getpgrp()})
    with lease(tmp_path) as state:
        assert state.name.startswith(".fewia-supervisor-")
        assert state.parent == tmp_path
        assert state.stat().st_mode & 0o077 == 0


def test_ambiguous_launch_state_blocks(tmp_path: Path) -> None:
    _lock(tmp_path, {"state": "launching", "pid": None})
    with pytest.raises(RuntimeError, match="Prior writer"), lease(tmp_path):
        pass
    tmp_path.joinpath("fewia-supervisor.lock").write_text(str(tmp_path / "old"))
    (tmp_path / "old" / "status.json").write_text("{")
    with pytest.raises(RuntimeError, match="Prior writer"), lease(tmp_path):
        pass


def test_missing_status_blocks(tmp_path: Path) -> None:
    _lock(tmp_path, None)
    with pytest.raises(RuntimeError, match="Prior writer"), lease(tmp_path):
        pass
