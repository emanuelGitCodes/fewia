"""Test queue delivery contracts and JSON validation."""

import json
from uuid import uuid4

import pytest

from app.services.job_delivery import _job_id, _json_object


def test_job_id_rejects_duplicate_keys() -> None:
    job_id = str(uuid4())
    body = f'{{"job_id":"{job_id}","job_id":"{job_id}"}}'

    assert _job_id(body) is None


def test_job_id_requires_a_canonical_uuid() -> None:
    job_id = str(uuid4())

    assert _job_id(json.dumps({"job_id": job_id})) == job_id
    assert _job_id(json.dumps({"job_id": job_id.upper()})) is None


def test_job_id_enforces_the_bounded_envelope_length() -> None:
    job_id = str(uuid4())
    body = json.dumps({"job_id": job_id})
    bounded = body + (" " * (256 - len(body)))

    assert len(bounded) == 256
    assert _job_id(bounded) == job_id
    assert _job_id(bounded + " ") is None


def test_json_object_returns_a_deep_copy() -> None:
    original: dict[str, object] = {"nested": {"items": ["safe"]}}

    copied = _json_object(original)
    assert copied == original
    assert copied is not original
    assert copied["nested"] is not original["nested"]

    nested = original["nested"]
    assert isinstance(nested, dict)
    nested["items"] = ["changed"]
    assert copied == {"nested": {"items": ["safe"]}}


@pytest.mark.parametrize("value", [[], {1: "invalid"}, {"value": float("nan")}])
def test_json_object_rejects_non_json_objects(value: object) -> None:
    with pytest.raises(ValueError):
        _json_object(value)
