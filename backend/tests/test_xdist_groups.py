"""Tests for the xdist grouping of tests that reach the shared test database.

The names below are built from parts so this file does not name the database
and stays out of the group it checks.
"""

import gzip
import re
import tomllib
from pathlib import Path
from typing import cast

import conftest
import pytest
from conftest import (
    DATABASE_XDIST_GROUP,
    NO_DATABASE_MODULES,
    _runs_distributed,
    database_modules,
    mark_database_items,
    module_dependencies,
    pytest_collection_modifyitems,
    uses_test_database,
)

HELPER_NAME = "require_test_" + "database_url"
URL_NAME = "FEWIA_JOB_TEST_" + "DATABASE_URL"
EVALUATION_URL_NAME = "FEWIA_EVALUATION_" + "DATABASE_URL"
DATABASE_NAMES = [HELPER_NAME, URL_NAME, EVALUATION_URL_NAME]
TESTS_DIR = Path(__file__).resolve().parent
PYPROJECT = TESTS_DIR.parent / "pyproject.toml"
MISSED_BY_TEXT_RULE = [
    "test_bootstrap_hosting",
    "test_job_leases_postgres",
    "test_outbox_postgres",
    "test_sync_job",
]

GZIP_HEADER = r"\\x1f\\x8b\\x08\\x00"
ESCAPED_BYTE = r"(?:\\x[0-9a-f]{2}|\\[tnr\\']|[^\\])"
# The gzip header, then a four-byte mtime that is not all zero.
UNSTABLE_GZIP_ID = re.compile(GZIP_HEADER + r"(?!(?:\\x00){4})" + ESCAPED_BYTE + "{4}")


class StubItem:
    """Record the markers the hook adds, without a real collected test."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.markers: list[pytest.MarkDecorator] = []

    def add_marker(self, marker: pytest.MarkDecorator) -> None:
        self.markers.append(marker)


class StubConfig:
    """Answer the two questions `_runs_distributed` asks of a pytest config."""

    def __init__(
        self, options: dict[str, object] | None = None, *, worker: bool = False
    ) -> None:
        self.options = options or {}
        if worker:
            self.workerinput = {"workerid": "gw0"}

    def getoption(self, name: str, default: object = None) -> object:
        return self.options.get(name, default)


def as_config(stub: StubConfig) -> pytest.Config:
    return cast(pytest.Config, stub)


def group_names(item: pytest.Item) -> list[object]:
    return [
        marker.args[0] if marker.args else None
        for marker in item.iter_markers(name="xdist_group")
    ]


def real_sources() -> dict[str, str]:
    return {
        path.stem: path.read_text(encoding="utf-8")
        for path in TESTS_DIR.glob("test_*.py")
    }


def escaped_id(value: bytes) -> str:
    """Escape bytes the way pytest writes them into a test id."""
    return repr(value)[2:-1]


@pytest.mark.parametrize("name", DATABASE_NAMES)
def test_uses_test_database_is_true_for_each_database_name(name: str) -> None:
    assert uses_test_database(f"url = {name}()")


@pytest.mark.parametrize(
    "source",
    ["", "def test_it() -> None:\n    assert True\n", "FEWIA_REQUIRE_DB = 1"],
)
def test_uses_test_database_is_false_for_other_text(source: str) -> None:
    assert not uses_test_database(source)


def test_this_file_does_not_name_the_database_as_one_literal() -> None:
    assert not uses_test_database(Path(__file__).read_text(encoding="utf-8"))


def test_database_group_name_is_database() -> None:
    assert DATABASE_XDIST_GROUP == "database"


def test_no_database_modules_are_the_five_that_never_connect() -> None:
    assert NO_DATABASE_MODULES == frozenset(
        {
            "test_openai_compose_launcher",
            "test_evaluation_cli_config",
            "test_cloud_database_config",
            "test_database_gate",
            "test_xdist_groups",
        }
    )


@pytest.mark.parametrize("stem", sorted(NO_DATABASE_MODULES))
def test_each_no_database_module_is_a_file_that_exists(stem: str) -> None:
    assert (TESTS_DIR / f"{stem}.py").is_file()


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("", set()),
        ("import test_a", {"test_a"}),
        ("import tests.test_a", {"test_a"}),
        ("import tests.test_a as alias", {"test_a"}),
        ("from test_a import f", {"test_a", "f"}),
        ("from tests import test_a", {"tests", "test_a"}),
        ("from tests.test_a import f, g", {"test_a", "f", "g"}),
        ("from . import test_a", {"test_a"}),
        ("def f() -> None:\n    import test_a\n", {"test_a"}),
        ('pytest_plugins = ["test_a", "pkg.test_b"]', {"test_a", "test_b"}),
        ('pytest_plugins = "test_a"', {"test_a"}),
        ('other_plugins = ["test_a"]', set()),
        ("def broken(:\n", set()),
    ],
)
def test_module_dependencies_reads_imports_and_plugins(
    source: str, expected: set[str]
) -> None:
    assert module_dependencies(source) == frozenset(expected)


def test_database_modules_starts_with_each_module_naming_a_database_name() -> None:
    sources = {
        f"test_{index}": f"x = {name}" for index, name in enumerate(DATABASE_NAMES)
    }
    sources["test_plain"] = "x = 1"

    assert database_modules(sources) == frozenset(
        f"test_{index}" for index in range(len(DATABASE_NAMES))
    )


@pytest.mark.parametrize(
    "importing_source",
    [
        "import test_a",
        "import tests.test_a",
        "from test_a import f",
        "from tests import test_a",
        "from tests.test_a import f",
        'pytest_plugins = ["test_a"]',
    ],
)
def test_database_modules_adds_a_module_that_imports_a_database_module(
    importing_source: str,
) -> None:
    sources = {
        "test_a": f"url = {HELPER_NAME}()",
        "test_b": importing_source,
        "test_c": "import os",
    }

    assert database_modules(sources) == frozenset({"test_a", "test_b"})


def test_database_modules_follows_a_chain_of_three_modules() -> None:
    sources = {
        "test_c": "from test_b import f",
        "test_unrelated": "import test_d",
        "test_b": "from tests import test_a",
        "test_a": f"url = {URL_NAME}",
        "test_d": "x = 1",
    }

    assert database_modules(sources) == frozenset({"test_a", "test_b", "test_c"})


def test_database_modules_follows_a_dependency_cycle_once() -> None:
    sources = {
        "test_a": "import test_b",
        "test_b": f"import test_a\nurl = {HELPER_NAME}()",
    }

    assert database_modules(sources) == frozenset({"test_a", "test_b"})


def test_database_modules_keeps_a_no_database_module_out() -> None:
    stem = sorted(NO_DATABASE_MODULES)[0]
    sources = {stem: f"url = {HELPER_NAME}()"}

    assert database_modules(sources) == frozenset()


def test_database_modules_keeps_out_an_importer_of_only_a_no_database_module() -> None:
    stem = sorted(NO_DATABASE_MODULES)[0]
    sources = {
        stem: f"url = {HELPER_NAME}()",
        "test_importer": f"import {stem}",
        "test_real": f"url = {HELPER_NAME}()",
    }

    assert database_modules(sources) == frozenset({"test_real"})


def test_database_modules_does_not_pass_through_a_no_database_module() -> None:
    stem = sorted(NO_DATABASE_MODULES)[0]
    sources = {
        "test_real": f"url = {HELPER_NAME}()",
        stem: "import test_real",
        "test_importer": f"import {stem}",
    }

    assert database_modules(sources) == frozenset({"test_real"})


def test_real_tree_includes_the_modules_the_text_rule_missed() -> None:
    assert set(MISSED_BY_TEXT_RULE) <= database_modules(real_sources())


def test_real_tree_excludes_every_no_database_module() -> None:
    assert not NO_DATABASE_MODULES & database_modules(real_sources())


def test_real_items_from_the_modules_the_text_rule_missed_carry_the_group(
    request: pytest.FixtureRequest,
) -> None:
    items = request.session.items
    if not _runs_distributed(request.config):
        assert all(not group_names(item) for item in items)
        return
    missed = [item for item in items if item.path.stem in MISSED_BY_TEXT_RULE]
    if not missed:
        pytest.skip("None of the modules the text rule missed is collected.")
    for item in missed:
        assert group_names(item) == [DATABASE_XDIST_GROUP], item.nodeid


def test_collected_items_carry_the_group_only_when_the_module_reaches_a_database(
    request: pytest.FixtureRequest,
) -> None:
    items = request.session.items
    assert items
    distributed = _runs_distributed(request.config)
    members = database_modules(real_sources())
    for item in items:
        grouped = distributed and item.path.stem in members
        expected = [DATABASE_XDIST_GROUP] if grouped else []
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


def test_mark_database_items_marks_only_reaching_modules_and_keeps_order() -> None:
    database_path = Path("test_with_database.py")
    importer_path = Path("test_with_importer.py")
    plain_path = Path("test_plain.py")
    sources = {
        database_path.stem: f"url = {HELPER_NAME}()\n",
        importer_path.stem: f"from tests import {database_path.stem}\n",
        plain_path.stem: "def test_plain() -> None: ...\n",
    }
    items = [
        StubItem(plain_path),
        StubItem(database_path),
        StubItem(importer_path),
        StubItem(database_path),
        StubItem(plain_path),
    ]
    original_order = list(items)

    mark_database_items(cast(list[pytest.Item], items), sources)

    assert items == original_order
    for item in items:
        if item.path == plain_path:
            assert item.markers == []
        else:
            assert len(item.markers) == 1
            marker = item.markers[0].mark
            assert marker.name == "xdist_group"
            assert marker.args == (DATABASE_XDIST_GROUP,)


def test_hook_reads_each_test_module_in_the_directory_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reads: list[Path] = []
    original_read_text = Path.read_text

    def counting_read_text(self: Path, encoding: str | None = None) -> str:
        reads.append(self)
        return original_read_text(self, encoding=encoding)

    monkeypatch.setattr(Path, "read_text", counting_read_text)
    items = [StubItem(Path("test_plain.py")) for _ in range(3)]

    pytest_collection_modifyitems(
        as_config(StubConfig(worker=True)), cast(list[pytest.Item], items)
    )

    test_modules = sorted(TESTS_DIR.glob("test_*.py"))
    assert sorted(path for path in reads if path.parent == TESTS_DIR) == test_modules
    assert all(not item.markers for item in items)


def test_runs_distributed_is_true_on_an_xdist_worker() -> None:
    assert _runs_distributed(as_config(StubConfig(worker=True)))


def test_runs_distributed_is_true_on_the_xdist_controller() -> None:
    assert _runs_distributed(as_config(StubConfig({"numprocesses": 4})))


@pytest.mark.parametrize("numprocesses", [0, None])
def test_runs_distributed_is_false_on_one_process(numprocesses: int | None) -> None:
    config = StubConfig({"numprocesses": numprocesses})

    assert not _runs_distributed(as_config(config))


def test_runs_distributed_is_false_when_xdist_is_not_installed() -> None:
    assert not _runs_distributed(as_config(StubConfig()))


def test_hook_reads_no_file_and_marks_no_item_on_one_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reads: list[object] = []

    def recording_read() -> dict[str, str]:
        reads.append(None)
        return {"test_with_database": f"url = {HELPER_NAME}()\n"}

    monkeypatch.setattr(conftest, "_read_test_sources", recording_read)
    items = [StubItem(Path("test_with_database.py")) for _ in range(2)]

    pytest_collection_modifyitems(
        as_config(StubConfig({"numprocesses": 0})), cast(list[pytest.Item], items)
    )

    assert reads == []
    assert all(not item.markers for item in items)


@pytest.mark.parametrize(
    "config",
    [StubConfig(worker=True), StubConfig({"numprocesses": 4})],
    ids=["worker", "controller"],
)
def test_hook_marks_the_items_of_a_database_module_when_distributed(
    monkeypatch: pytest.MonkeyPatch, config: StubConfig
) -> None:
    monkeypatch.setattr(
        conftest,
        "_read_test_sources",
        lambda: {
            "test_with_database": f"url = {HELPER_NAME}()\n",
            "test_plain": "x = 1\n",
        },
    )
    database_items = [StubItem(Path("test_with_database.py")) for _ in range(2)]
    plain_item = StubItem(Path("test_plain.py"))

    pytest_collection_modifyitems(
        as_config(config), cast(list[pytest.Item], [*database_items, plain_item])
    )

    for item in database_items:
        assert [marker.mark.args for marker in item.markers] == [
            (DATABASE_XDIST_GROUP,)
        ]
    assert plain_item.markers == []


def test_unstable_gzip_id_matches_a_gzip_id_with_a_nonzero_mtime() -> None:
    value = escaped_id(gzip.compress(b"x", mtime=5))

    assert UNSTABLE_GZIP_ID.search(f"test_it[{value}]")


def test_unstable_gzip_id_ignores_a_gzip_id_with_a_zero_mtime() -> None:
    value = escaped_id(gzip.compress(b"x", mtime=0))

    assert value.startswith(r"\x1f\x8b\x08\x00")
    assert not UNSTABLE_GZIP_ID.search(f"test_it[{value}]")


def test_unstable_gzip_id_ignores_ids_without_a_gzip_header() -> None:
    assert not UNSTABLE_GZIP_ID.search("tests/test_it.py::test_it[plain-id]")


def test_collected_ids_do_not_carry_a_gzip_timestamp(
    request: pytest.FixtureRequest,
) -> None:
    items = request.session.items
    assert items
    for item in items:
        assert not UNSTABLE_GZIP_ID.search(item.nodeid), item.nodeid


def test_pytest_addopts_sets_loadgroup_and_starts_no_workers() -> None:
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    addopts = config["tool"]["pytest"]["ini_options"]["addopts"]
    assert addopts == "--dist loadgroup"
    assert "-n" not in addopts
