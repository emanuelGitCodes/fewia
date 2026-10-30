import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.deps import get_kroger_client
from app.provider_settings import GroceryProviderSettings
from app.providers.kroger import KrogerClient


@pytest.fixture(autouse=True)
def _clear_kroger_cache() -> Iterator[None]:
    get_kroger_client.cache_clear()
    yield
    get_kroger_client.cache_clear()


def test_get_kroger_client_none_without_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.deps.load_provider_settings", lambda: GroceryProviderSettings()
    )
    assert get_kroger_client() is None


def test_get_kroger_client_none_when_files_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "app.deps.load_provider_settings",
        lambda: GroceryProviderSettings(
            kroger_client_id_file=tmp_path / "no-id",
            kroger_secret_file=tmp_path / "no-secret",
        ),
    )
    assert get_kroger_client() is None


def test_concurrent_first_calls_build_one_kroger_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    barrier = threading.Barrier(8, timeout=5)
    built: list[object] = []

    def slow_build(settings: object) -> object:
        del settings
        time.sleep(0.05)
        client = object()
        built.append(client)
        return client

    monkeypatch.setattr(
        "app.deps.load_provider_settings", lambda: GroceryProviderSettings()
    )
    monkeypatch.setattr("app.deps.build_kroger", slow_build)
    results: list[object] = []

    def work() -> None:
        barrier.wait()
        results.append(get_kroger_client())

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert len(built) == 1
    assert results == built * 8


def test_get_kroger_client_built_from_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    id_file = tmp_path / "id"
    secret_file = tmp_path / "secret"
    id_file.write_text("invented-id\n")
    secret_file.write_text("invented-secret\n")
    id_file.chmod(0o600)
    secret_file.chmod(0o600)
    monkeypatch.setattr(
        "app.deps.load_provider_settings",
        lambda: GroceryProviderSettings(
            kroger_client_id_file=id_file, kroger_secret_file=secret_file
        ),
    )
    client = get_kroger_client()
    assert isinstance(client, KrogerClient)
    assert get_kroger_client() is client
