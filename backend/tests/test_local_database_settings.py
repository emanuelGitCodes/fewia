from pathlib import Path

import pytest

from app.local_database_settings import DEFAULT_DATABASE_URL, local_database_url
from app.local_secret_state import LocalStateError


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "FEWIA_LOCAL_ADMIN_PASSWORD_FILE",
        "FEWIA_LOCAL_DATABASE_PASSWORD_FILE",
        "DATABASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)


def test_default_has_no_password() -> None:
    assert DEFAULT_DATABASE_URL == "postgresql+psycopg://fewia_app@localhost:5432/fewia"
    assert local_database_url() is None


def test_runtime_never_reads_admin_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = tmp_path / "runtime"
    runtime.write_text("R" * 32)
    runtime.chmod(0o600)
    monkeypatch.setenv("FEWIA_LOCAL_DATABASE_PASSWORD_FILE", str(runtime))
    monkeypatch.setenv("FEWIA_LOCAL_ADMIN_PASSWORD_FILE", str(tmp_path / "missing"))
    url = local_database_url()
    assert url is not None
    assert url.username == "fewia_app"
    assert url.password == "R" * 32
    assert "R" * 32 not in repr(url)


def test_admin_url_is_explicit_and_separate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = tmp_path / "admin"
    admin.write_text("A" * 32)
    admin.chmod(0o600)
    monkeypatch.setenv("FEWIA_LOCAL_ADMIN_PASSWORD_FILE", str(admin))
    assert local_database_url() is None
    url = local_database_url(admin=True)
    assert url is not None
    assert url.username == "fewia"
    assert url.password == "A" * 32


def test_admin_file_is_required() -> None:
    with pytest.raises(LocalStateError):
        local_database_url(admin=True)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://fewia_app@external.invalid:5432/fewia",
        "postgresql+psycopg://fewia_app@postgres:5433/fewia",
        "postgresql+psycopg://fewia_app@postgres:5432/other",
        "postgresql+psycopg://fewia@postgres:5432/fewia",
        "postgresql+psycopg://fewia_app:password@postgres:5432/fewia",
        "postgresql+psycopg://fewia_app@postgres:5432/fewia?host=external.invalid",
        "sqlite:///database",
    ],
)
def test_secret_cannot_route_to_another_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("FEWIA_LOCAL_DATABASE_PASSWORD_FILE", str(tmp_path / "absent"))
    with pytest.raises(LocalStateError, match="target"):
        local_database_url()
