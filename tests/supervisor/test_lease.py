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
