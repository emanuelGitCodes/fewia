"""Test P05 local resource fixture guards and cleanup."""

from unittest.mock import MagicMock, Mock

import p05_resources
import pytest
from p05_resources import (
    _close_if_possible,
    _create_schema,
    _delete_owned_artifact_keys,
    _drop_schema,
    _normalized_queue_url,
    _owned_artifact_key,
    _queue_name_for,
    _quote_schema,
    _require_quoted_schema,
    _schema_name_for,
    _validate_database_url,
    _validate_floci_endpoint,
    local_resources,
)
from sqlalchemy.sql.elements import TextClause

from app.providers.local_artifacts import LocalArtifactStore
from app.providers.local_sqs import ALLOWED_ENDPOINTS

_ENDPOINT = "http://127.0.0.1:4566"
_LOCAL_POSTGRES = "postgresql+psycopg://fewia:fewia@127.0.0.1:5432/fewia"
_LOCAL_POSTGRES_HOST = "postgresql+psycopg://fewia:fewia@localhost:5432/fewia"
_SECRET_URL = "postgresql+psycopg://fewia:super-secret@example.com:5432/fewia"
_HASH_A = "a" * 64
_HASH_B = "b" * 64
_VALID_KEY_A = f"evaluation/{_HASH_A}.json"
_VALID_KEY_B = f"evaluation/{_HASH_B}.json"
_TIMEOUT_OPTIONS = "-c statement_timeout=10000 -c lock_timeout=3000"


class FakeDeleteClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []
        self.fail_key: str | None = None

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        self.calls.append({"Bucket": Bucket, "Key": Key})
        if Key == self.fail_key:
            raise RuntimeError("delete failed")

    def put_object(self, **kwargs: object) -> object:
        del kwargs
        return {}


def _patch_constructors(monkeypatch: pytest.MonkeyPatch) -> dict[str, Mock]:
    mocks = {
        "create_engine": Mock(name="create_engine"),
        "LocalSqsSender": Mock(name="LocalSqsSender"),
        "LocalSqsConsumer": Mock(name="LocalSqsConsumer"),
        "LocalArtifactStore": Mock(name="LocalArtifactStore"),
    }
    monkeypatch.setattr(p05_resources, "create_engine", mocks["create_engine"])
    monkeypatch.setattr(p05_resources, "LocalSqsSender", mocks["LocalSqsSender"])
    monkeypatch.setattr(p05_resources, "LocalSqsConsumer", mocks["LocalSqsConsumer"])
    monkeypatch.setattr(
        p05_resources, "LocalArtifactStore", mocks["LocalArtifactStore"]
    )
    return mocks


def _assert_not_constructed(mocks: dict[str, Mock]) -> None:
    for mock in mocks.values():
        mock.assert_not_called()


def _set_p05_env(
    monkeypatch: pytest.MonkeyPatch,
    database_url: str | None,
    endpoint: str | None,
) -> None:
    if database_url is None:
        monkeypatch.delenv("FEWIA_P05_DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("FEWIA_P05_DATABASE_URL", database_url)
    if endpoint is None:
        monkeypatch.delenv("FEWIA_P05_FLOCI_ENDPOINT", raising=False)
    else:
        monkeypatch.setenv("FEWIA_P05_FLOCI_ENDPOINT", endpoint)


@pytest.mark.parametrize(
    ("database_url", "endpoint"),
    [
        (None, _ENDPOINT),
        (_LOCAL_POSTGRES, None),
        (None, None),
        ("", _ENDPOINT),
        (_LOCAL_POSTGRES, ""),
    ],
)
def test_missing_p05_env_skips_before_constructors(
    monkeypatch: pytest.MonkeyPatch,
    database_url: str | None,
    endpoint: str | None,
) -> None:
    _set_p05_env(monkeypatch, database_url, endpoint)
    monkeypatch.setenv("DATABASE_URL", _SECRET_URL)
    mocks = _patch_constructors(monkeypatch)

    with pytest.raises(pytest.skip.Exception) as caught:
        with local_resources():
            raise AssertionError("local_resources MUST skip")

    message = str(caught.value)
    assert "FEWIA_P05_DATABASE_URL" in message
    assert "FEWIA_P05_FLOCI_ENDPOINT" in message
    assert "super-secret" not in message
    assert "example.com" not in message
    _assert_not_constructed(mocks)


@pytest.mark.parametrize(
    "database_url",
    [
        "sqlite://",
        _SECRET_URL,
        "postgresql://fewia@10.0.0.1:5432/fewia",
        "postgresql://fewia@postgres:5432/fewia",
        "postgresql://fewia@0.0.0.0:5432/fewia",
        "postgresql://fewia:fewia@localhost:5432/fewia",
        "mysql://fewia@localhost:3306/fewia",
        "not-a-url",
        "postgresql+psycopg://fewia:fewia@127.0.0.1:5432/fewia?host=/tmp",
        "postgresql+psycopg://fewia:fewia@127.0.0.1:5432/fewia?service=fewia",
        (
            "postgresql+psycopg://fewia:fewia@127.0.0.1:5432/fewia"
            "?options=-csearch_path=public"
        ),
    ],
)
def test_invalid_database_url_rejects_before_constructors(
    monkeypatch: pytest.MonkeyPatch,
    database_url: str,
) -> None:
    _set_p05_env(monkeypatch, database_url, _ENDPOINT)
    mocks = _patch_constructors(monkeypatch)

    with pytest.raises(ValueError, match="PostgreSQL") as caught:
        with local_resources():
            raise AssertionError("local_resources MUST reject the database URL")

    message = str(caught.value)
    assert database_url not in message
    assert "super-secret" not in message
    assert "example.com" not in message
    _assert_not_constructed(mocks)


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://127.0.0.1:4567",
        "https://sqs.us-east-1.amazonaws.com",
        "http://floci:4567",
        "http://localhost:4566/extra",
    ],
)
def test_invalid_floci_endpoint_rejects_before_constructors(
    monkeypatch: pytest.MonkeyPatch,
    endpoint: str,
) -> None:
    _set_p05_env(monkeypatch, _LOCAL_POSTGRES, endpoint)
    mocks = _patch_constructors(monkeypatch)

    with pytest.raises(ValueError, match="Floci") as caught:
        with local_resources():
            raise AssertionError("local_resources MUST reject the endpoint")

    assert endpoint not in str(caught.value)
    _assert_not_constructed(mocks)


def _assert_timeout_connect_args(captured: dict[str, object]) -> dict[str, object]:
    assert captured["url"] == _LOCAL_POSTGRES
    assert captured["pool_pre_ping"] is True
    assert captured["pool_timeout"] == 3
    connect_args = captured["connect_args"]
    assert isinstance(connect_args, dict)
    assert connect_args["connect_timeout"] == 3
    options = connect_args["options"]
    assert isinstance(options, str)
    assert "statement_timeout=10000" in options
    assert "lock_timeout=3000" in options
    return connect_args


def test_create_engine_admin_keeps_default_path_and_timeouts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_create_engine(url: str, **kwargs: object) -> MagicMock:
        captured["url"] = url
        captured.update(kwargs)
        return MagicMock()

    monkeypatch.setattr(p05_resources, "create_engine", fake_create_engine)
    engine = p05_resources._engine(_LOCAL_POSTGRES)
    assert isinstance(engine, MagicMock)
    connect_args = _assert_timeout_connect_args(captured)
    assert connect_args["options"] == _TIMEOUT_OPTIONS
    assert "search_path" not in str(connect_args["options"])


def test_create_engine_scoped_uses_private_search_path_and_timeouts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    schema_name = _schema_name_for("ab" * 16)

    def fake_create_engine(url: str, **kwargs: object) -> MagicMock:
        captured["url"] = url
        captured.update(kwargs)
        return MagicMock()

    monkeypatch.setattr(p05_resources, "create_engine", fake_create_engine)
    engine = p05_resources._engine(_LOCAL_POSTGRES, schema_name=schema_name)
    assert isinstance(engine, MagicMock)
    connect_args = _assert_timeout_connect_args(captured)
    options = connect_args["options"]
    assert options == f"-c search_path={schema_name} {_TIMEOUT_OPTIONS}"
    assert "public" not in str(options)


def test_create_engine_rejects_invalid_schema_before_constructor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = Mock()
    monkeypatch.setattr(p05_resources, "create_engine", fake)
    with pytest.raises(ValueError, match="generated UUID"):
        p05_resources._engine(_LOCAL_POSTGRES, schema_name="public")
    with pytest.raises(ValueError, match="generated UUID"):
        p05_resources._engine(
            _LOCAL_POSTGRES,
            schema_name="p05_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa, public",
        )
    fake.assert_not_called()


def test_localhost_psycopg_urls_pass_validation() -> None:
    _validate_database_url(_LOCAL_POSTGRES)
    _validate_database_url(_LOCAL_POSTGRES_HOST)


@pytest.mark.parametrize("endpoint", sorted(ALLOWED_ENDPOINTS))
def test_allowed_floci_endpoints_pass_validation(endpoint: str) -> None:
    _validate_floci_endpoint(endpoint)


def test_quote_schema_and_queue_name_use_uuid_hex() -> None:
    run_id = "ab" * 16
    assert _schema_name_for(run_id) == f"p05_{run_id}"
    assert _quote_schema(run_id) == f'"p05_{run_id}"'
    assert _queue_name_for(run_id) == f"fewia-p05-{run_id}"


@pytest.mark.parametrize(
    "run_id",
    ["", "abc", "AB" * 16, "ab" * 16 + "c", "abcd;drop", "p05_" + "a" * 32],
)
def test_quote_schema_rejects_non_hex_run_id(run_id: str) -> None:
    with pytest.raises(ValueError, match="UUID hex"):
        _quote_schema(run_id)
    with pytest.raises(ValueError, match="UUID hex"):
        _queue_name_for(run_id)


def test_schema_sql_rejects_unquoted_input() -> None:
    engine = MagicMock()
    with pytest.raises(ValueError, match="generated UUID"):
        _create_schema(engine, "p05_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    with pytest.raises(ValueError, match="generated UUID"):
        _drop_schema(engine, '"p05_aa"; DROP SCHEMA public')
    engine.begin.assert_not_called()


def test_create_and_drop_schema_quote_generated_name() -> None:
    engine = MagicMock()
    connection = MagicMock()
    engine.begin.return_value.__enter__.return_value = connection
    engine.begin.return_value.__exit__.return_value = None
    quoted = _quote_schema("cd" * 16)

    _create_schema(engine, quoted)
    _drop_schema(engine, quoted)

    created = connection.execute.call_args_list[0].args[0]
    dropped = connection.execute.call_args_list[1].args[0]
    assert isinstance(created, TextClause)
    assert isinstance(dropped, TextClause)
    assert created.text == f"CREATE SCHEMA {quoted}"
    assert dropped.text == f"DROP SCHEMA IF EXISTS {quoted} CASCADE"


def test_require_quoted_schema_accepts_generated_form() -> None:
    quoted = _quote_schema("ef" * 16)
    assert _require_quoted_schema(quoted) == quoted


@pytest.mark.parametrize(
    "key,owned",
    [
        (_VALID_KEY_A, True),
        (_VALID_KEY_B, True),
        (f"evaluation/{'A' * 64}.json", False),
        (f"evaluation/{'a' * 63}.json", False),
        (f"evaluation/{'a' * 65}.json", False),
        (f"evaluation/{_HASH_A}", False),
        (f"evaluation/{_HASH_A}.json.backup", False),
        (f"other/{_HASH_A}.json", False),
        (f"evaluation/{_HASH_A}.json/extra", False),
        (f"evaluation/../{_HASH_A}.json", False),
        ("evaluation/", False),
        ("", False),
    ],
)
def test_owned_artifact_key_shape(key: str, owned: bool) -> None:
    assert _owned_artifact_key(key) is owned


def test_delete_owned_artifact_keys_deletes_only_valid_eval_keys() -> None:
    client = FakeDeleteClient()
    store = LocalArtifactStore(_ENDPOINT, client=client)
    keys = [
        _VALID_KEY_A,
        "secrets/credential.json",
        f"evaluation/{_HASH_A}.json.extra",
        _VALID_KEY_B,
        "evaluation/not-a-hash.json",
    ]

    _delete_owned_artifact_keys(store, keys)

    assert client.calls == [
        {"Bucket": "fewia-eval", "Key": _VALID_KEY_B},
        {"Bucket": "fewia-eval", "Key": _VALID_KEY_A},
    ]


def test_delete_owned_artifact_keys_continues_after_one_failure() -> None:
    client = FakeDeleteClient()
    client.fail_key = _VALID_KEY_B
    store = LocalArtifactStore(_ENDPOINT, client=client)

    with pytest.raises(RuntimeError, match="delete failed"):
        _delete_owned_artifact_keys(store, [_VALID_KEY_A, _VALID_KEY_B])

    assert client.calls == [
        {"Bucket": "fewia-eval", "Key": _VALID_KEY_B},
        {"Bucket": "fewia-eval", "Key": _VALID_KEY_A},
    ]


def test_close_if_possible_skips_missing_close() -> None:
    _close_if_possible(object())
    closed = Mock()
    _close_if_possible(closed)
    closed.close.assert_called_once()


def test_normalized_queue_url_rejects_invalid_response() -> None:
    queue_name = _queue_name_for("34" * 16)
    with pytest.raises(RuntimeError, match="queue URL"):
        _normalized_queue_url("not-a-dict", _ENDPOINT, queue_name)
    with pytest.raises(RuntimeError, match="queue URL"):
        _normalized_queue_url({"QueueUrl": 1}, _ENDPOINT, queue_name)
    with pytest.raises(RuntimeError, match="queue URL") as caught:
        _normalized_queue_url(
            {"QueueUrl": "https://sqs.amazonaws.com/000000000000/secret"},
            _ENDPOINT,
            queue_name,
        )
    assert "amazonaws" not in str(caught.value)
    assert "secret" not in str(caught.value)


def test_normalized_queue_url_rewrites_to_endpoint() -> None:
    queue_name = _queue_name_for("56" * 16)
    raw = f"http://localhost:4566/000000000000/{queue_name}"
    assert (
        _normalized_queue_url({"QueueUrl": raw}, _ENDPOINT, queue_name)
        == f"{_ENDPOINT}/000000000000/{queue_name}"
    )


def _mock_engine() -> MagicMock:
    engine = MagicMock()
    connection = MagicMock()
    engine.begin.return_value.__enter__.return_value = connection
    engine.begin.return_value.__exit__.return_value = None
    return engine


def _install_resource_fakes(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[
    MagicMock,
    MagicMock,
    Mock,
    Mock,
    Mock,
    FakeDeleteClient,
    list[str | None],
]:
    admin_engine = _mock_engine()
    scoped_engine = _mock_engine()
    engines = iter((admin_engine, scoped_engine))
    schema_names: list[str | None] = []

    def fake_engine(database_url: str, *, schema_name: str | None = None) -> MagicMock:
        assert database_url == _LOCAL_POSTGRES
        schema_names.append(schema_name)
        return next(engines)

    monkeypatch.setattr(p05_resources, "_engine", fake_engine)
    monkeypatch.setattr(p05_resources.Base.metadata, "create_all", Mock())

    sender = Mock()
    admin_client = Mock()
    sender._client = admin_client

    def create_queue(*, QueueName: str) -> dict[str, str]:
        return {"QueueUrl": f"{_ENDPOINT}/000000000000/{QueueName}"}

    admin_client.create_queue.side_effect = create_queue
    monkeypatch.setattr(p05_resources, "LocalSqsSender", Mock(return_value=sender))

    consumer = Mock()
    monkeypatch.setattr(p05_resources, "LocalSqsConsumer", Mock(return_value=consumer))

    artifact_client = FakeDeleteClient()
    artifacts = LocalArtifactStore(_ENDPOINT, client=artifact_client)
    monkeypatch.setattr(
        p05_resources, "LocalArtifactStore", Mock(return_value=artifacts)
    )
    return (
        admin_engine,
        scoped_engine,
        sender,
        admin_client,
        consumer,
        artifact_client,
        schema_names,
    )


def test_local_resources_constructs_and_cleans_with_fakes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_p05_env(monkeypatch, _LOCAL_POSTGRES, _ENDPOINT)
    (
        admin_engine,
        scoped_engine,
        sender,
        admin_client,
        consumer,
        artifact_client,
        schema_names,
    ) = _install_resource_fakes(monkeypatch)
    sender_cls = p05_resources.LocalSqsSender
    consumer_cls = p05_resources.LocalSqsConsumer

    with local_resources() as resources:
        queue_name = f"fewia-p05-{resources.run_id}"
        quoted = f'"p05_{resources.run_id}"'
        assert resources.sender is sender
        assert resources.consumer is consumer
        assert consumer._queue_name == queue_name
        assert resources.queue_url == f"{_ENDPOINT}/000000000000/{queue_name}"
        resources.owned_artifact_keys.append(_VALID_KEY_A)
        resources.owned_artifact_keys.append("not-an-owned-key")
        create_all = p05_resources.Base.metadata.create_all
        create_all.assert_called_once()
        created_tables = create_all.call_args.kwargs["tables"]
        assert [table.name for table in created_tables] == [
            "users",
            "jobs",
            "job_outbox",
            "grocery_evidence",
            "shopping_handoffs",
        ]
        assert create_all.call_args.kwargs["bind"] is scoped_engine
        assert schema_names == [None, f"p05_{resources.run_id}"]

    sender_cls.assert_called_once_with(_ENDPOINT)
    consumer_cls.assert_called_once_with(_ENDPOINT, "sync")
    admin_client.create_queue.assert_called_once_with(QueueName=queue_name)
    admin_client.delete_queue.assert_called_once_with(
        QueueUrl=f"{_ENDPOINT}/000000000000/{queue_name}"
    )
    admin_client.close.assert_called_once()
    scoped_engine.dispose.assert_called_once()
    admin_engine.dispose.assert_called_once()
    assert artifact_client.calls == [{"Bucket": "fewia-eval", "Key": _VALID_KEY_A}]
    execute = admin_engine.begin.return_value.__enter__.return_value.execute
    statements = [call.args[0].text for call in execute.call_args_list]
    assert statements == [
        f"CREATE SCHEMA {quoted}",
        f"DROP SCHEMA IF EXISTS {quoted} CASCADE",
    ]


def test_local_resources_drop_schema_after_queue_delete_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_p05_env(monkeypatch, _LOCAL_POSTGRES, _ENDPOINT)
    admin_engine, scoped_engine, _sender, admin_client, _consumer, _keys, _names = (
        _install_resource_fakes(monkeypatch)
    )
    admin_client.delete_queue.side_effect = RuntimeError("queue delete failed")

    with pytest.raises(RuntimeError, match="queue delete failed"):
        with local_resources():
            pass

    execute = admin_engine.begin.return_value.__enter__.return_value.execute
    statements = [call.args[0].text for call in execute.call_args_list]
    assert statements[0].startswith("CREATE SCHEMA ")
    assert statements[1].startswith("DROP SCHEMA IF EXISTS ")
    assert statements[1].endswith(" CASCADE")
    scoped_engine.dispose.assert_called_once()
    admin_engine.dispose.assert_called_once()
    admin_client.close.assert_called_once()


def test_local_resources_drops_schema_after_scoped_dispose_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_p05_env(monkeypatch, _LOCAL_POSTGRES, _ENDPOINT)
    admin_engine, scoped_engine, _sender, _admin, _consumer, _keys, _names = (
        _install_resource_fakes(monkeypatch)
    )
    order: list[str] = []

    def failing_scoped_dispose() -> None:
        order.append("scoped_dispose")
        raise RuntimeError("dispose failed")

    scoped_engine.dispose.side_effect = failing_scoped_dispose

    original_drop = p05_resources._drop_schema

    def tracking_drop(engine: object, quoted_schema: str) -> None:
        order.append("drop")
        original_drop(engine, quoted_schema)

    def tracking_admin_dispose() -> None:
        order.append("admin_dispose")

    monkeypatch.setattr(p05_resources, "_drop_schema", tracking_drop)
    admin_engine.dispose.side_effect = tracking_admin_dispose

    with pytest.raises(RuntimeError, match="dispose failed"):
        with local_resources():
            pass

    assert order[-3:] == ["scoped_dispose", "drop", "admin_dispose"]
    execute = admin_engine.begin.return_value.__enter__.return_value.execute
    statements = [call.args[0].text for call in execute.call_args_list]
    assert statements[0].startswith("CREATE SCHEMA ")
    assert statements[1].startswith("DROP SCHEMA IF EXISTS ")


def test_local_resources_skips_drop_when_create_schema_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_p05_env(monkeypatch, _LOCAL_POSTGRES, _ENDPOINT)
    admin_engine, scoped_engine, _sender, _admin, _consumer, _keys, schema_names = (
        _install_resource_fakes(monkeypatch)
    )
    drop = Mock()
    monkeypatch.setattr(
        p05_resources,
        "_create_schema",
        Mock(side_effect=RuntimeError("create schema failed")),
    )
    monkeypatch.setattr(p05_resources, "_drop_schema", drop)

    with pytest.raises(RuntimeError, match="create schema failed"):
        with local_resources():
            raise AssertionError("local_resources MUST fail before yield")

    drop.assert_not_called()
    admin_engine.dispose.assert_called_once()
    scoped_engine.dispose.assert_not_called()
    assert schema_names == [None]
    p05_resources.Base.metadata.create_all.assert_not_called()
    p05_resources.LocalSqsSender.assert_not_called()


def test_local_resources_drops_schema_when_scoped_engine_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_p05_env(monkeypatch, _LOCAL_POSTGRES, _ENDPOINT)
    admin_engine = _mock_engine()
    schema_names: list[str | None] = []
    order: list[str] = []

    def fake_engine(database_url: str, *, schema_name: str | None = None) -> MagicMock:
        assert database_url == _LOCAL_POSTGRES
        schema_names.append(schema_name)
        if schema_name is not None:
            raise RuntimeError("scoped engine failed")
        return admin_engine

    def tracking_drop(engine: object, quoted_schema: str) -> None:
        order.append("drop")
        assert engine is admin_engine
        p05_resources._require_quoted_schema(quoted_schema)

    def tracking_admin_dispose() -> None:
        order.append("admin_dispose")

    monkeypatch.setattr(p05_resources, "_engine", fake_engine)
    monkeypatch.setattr(p05_resources, "_drop_schema", tracking_drop)
    admin_engine.dispose.side_effect = tracking_admin_dispose
    create_all = Mock()
    monkeypatch.setattr(p05_resources.Base.metadata, "create_all", create_all)
    sender_cls = Mock()
    monkeypatch.setattr(p05_resources, "LocalSqsSender", sender_cls)

    with pytest.raises(RuntimeError, match="scoped engine failed"):
        with local_resources():
            raise AssertionError("local_resources MUST fail before yield")

    assert order == ["drop", "admin_dispose"]
    execute = admin_engine.begin.return_value.__enter__.return_value.execute
    statements = [call.args[0].text for call in execute.call_args_list]
    assert len(statements) == 1
    assert statements[0].startswith("CREATE SCHEMA ")
    create_all.assert_not_called()
    sender_cls.assert_not_called()
    assert schema_names[0] is None
    assert schema_names[1] is not None
