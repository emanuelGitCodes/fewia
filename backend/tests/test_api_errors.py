"""Tests for API error responses."""

from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.main import app


def test_unknown_path_uses_the_api_error_envelope(client: TestClient) -> None:
    response = client.get("/missing")

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "Not Found"}}


def test_disallowed_method_uses_the_api_error_envelope(client: TestClient) -> None:
    response = client.post("/healthz")

    assert response.status_code == 405
    assert response.json() == {
        "error": {"code": "method_not_allowed", "message": "Method Not Allowed"}
    }


def test_unnamed_http_status_uses_a_fallback_error_code() -> None:
    test_app = FastAPI()
    test_app.exception_handlers.update(app.exception_handlers)

    @test_app.get("/test-http-status-599")
    def raise_unnamed_status() -> None:
        raise StarletteHTTPException(status_code=599, detail="Custom status")

    with TestClient(test_app) as client:
        response = client.get("/test-http-status-599")

    assert response.status_code == 599
    assert response.json() == {
        "error": {"code": "http_599", "message": "Custom status"}
    }


def test_existing_404_and_422_responses_keep_their_bodies(client: TestClient) -> None:
    not_found_response = client.get(f"/grocery/jobs/{uuid4()}")
    validation_response = client.get("/grocery/jobs/not-a-uuid")

    assert not_found_response.status_code == 404
    assert not_found_response.json() == {
        "error": {
            "code": "not_found",
            "message": "Job not found",
        }
    }
    assert validation_response.status_code == 422
    assert validation_response.json() == {
        "error": {
            "code": "validation_error",
            "message": "The request has invalid parameters.",
            "detail": [
                {
                    "type": "uuid_parsing",
                    "loc": ["path", "job_id"],
                    "msg": "Input should be a valid UUID, invalid character: "
                    "expected an optional prefix of `urn:uuid:` followed by "
                    "[0-9a-fA-F-], found `n` at 1",
                    "input": "not-a-uuid",
                    "ctx": {
                        "error": "invalid character: expected an optional prefix of "
                        "`urn:uuid:` followed by [0-9a-fA-F-], found `n` at 1"
                    },
                    "url": "https://errors.pydantic.dev/2.13/v/uuid_parsing",
                }
            ],
        }
    }
