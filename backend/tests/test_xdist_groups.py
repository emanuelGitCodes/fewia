"""Tests for the xdist grouping of tests that share the test database.

The names below are built from parts so this file does not name the database
and stays out of the group it checks.
"""

import tomllib
from pathlib import Path
from typing import cast

import pytest
from conftest import (
    DATABASE_XDIST_GROUP,
    pytest_collection_modifyitems,
    uses_test_database,
)

HELPER_NAME = "require_test_" + "database_url"
URL_NAME = "FEWIA_JOB_TEST_" + "DATABASE_URL"
PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


class StubItem:
    """Record the markers the hook adds, without a real collected test."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.markers: list[pytest.MarkDecorator] = []

    def add_marker(self, marker: pytest.MarkDecorator) -> None:
        self.markers.append(marker)


def group_names(item: pytest.Item) -> list[object]:
    return [
        marker.args[0] if marker.args else None
        for marker in item.iter_markers(name="xdist_group")
    ]


@pytest.mark.parametrize("name", [HELPER_NAME, URL_NAME])
def test_uses_test_database_is_true_for_each_database_name(name: str) -> None:
    assert uses_test_database(f"url = {name}()")


@pytest.mark.parametrize(
    "source",
    ["", "def test_it() -> None:\n    assert True\n", "FEWIA_REQUIRE_DB = 1"],
)
def test_uses_test_database_is_false_for_other_text(source: str) -> None:
    assert not uses_test_database(source)


def test_database_group_name_is_database() -> None:
    assert DATABASE_XDIST_GROUP == "database"


def test_collected_items_carry_the_group_only_when_the_module_names_the_database(
    request: pytest.FixtureRequest,
) -> None:
    items = request.session.items
    assert items
    names_database_by_path: dict[Path, bool] = {}
    for item in items:
        if item.path not in names_database_by_path:
            names_database_by_path[item.path] = uses_test_database(
                item.path.read_text(encoding="utf-8")
            )
        expected = [DATABASE_XDIST_GROUP] if names_database_by_path[item.path] else []
        assert group_names(item) == expected, item.nodeid


def test_xdist_worker_node_ids_carry_the_group_suffix(
    request: pytest.FixtureRequest,
) -> None:
    if not hasattr(request.config, "workerinput"):
        pytest.skip("Node ids get the group suffix only on xdist workers.")
    suffix = "@" + DATABASE_XDIST_GROUP
    for item in request.session.items:
        assert item.nodeid.endswith(suffix) == bool(group_names(item)), item.nodeid


def test_items_from_this_file_are_not_grouped(
    request: pytest.FixtureRequest,
) -> None:
    own = [item for item in request.session.items if item.path == Path(__file__)]
    assert own
    assert all(not group_names(item) for item in own)


def test_hook_marks_only_modules_that_name_the_database_and_keeps_order(
    tmp_path: Path,
) -> None:
    database_module = tmp_path / "test_with_database.py"
    database_module.write_text(f"url = {HELPER_NAME}()\n", encoding="utf-8")
    url_module = tmp_path / "test_with_url.py"
    url_module.write_text(f"import os\nos.environ['{URL_NAME}']\n", encoding="utf-8")
    plain_module = tmp_path / "test_plain.py"
    plain_module.write_text("def test_plain() -> None: ...\n", encoding="utf-8")
    items = [
        StubItem(plain_module),
        StubItem(database_module),
        StubItem(url_module),
        StubItem(database_module),
        StubItem(plain_module),
    ]
    original_order = list(items)

    pytest_collection_modifyitems(cast(list[pytest.Item], items))

    assert items == original_order
    for item in items:
        if item.path == plain_module:
            assert item.markers == []
        else:
            assert len(item.markers) == 1
            marker = item.markers[0].mark
            assert marker.name == "xdist_group"
            assert marker.args == (DATABASE_XDIST_GROUP,)


def test_hook_reads_each_module_source_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = tmp_path / "test_with_database.py"
    module.write_text(f"url = {HELPER_NAME}()\n", encoding="utf-8")
    reads: list[Path] = []
    original_read_text = Path.read_text

    def counting_read_text(self: Path, encoding: str | None = None) -> str:
        reads.append(self)
        return original_read_text(self, encoding=encoding)

    monkeypatch.setattr(Path, "read_text", counting_read_text)
    items = [StubItem(module) for _ in range(3)]

    pytest_collection_modifyitems(cast(list[pytest.Item], items))

    assert [path for path in reads if path == module] == [module]


def test_pytest_addopts_runs_workers_with_loadgroup() -> None:
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    addopts = config["tool"]["pytest"]["ini_options"]["addopts"]
    assert "-n 4" in addopts
    assert "--dist loadgroup" in addopts
