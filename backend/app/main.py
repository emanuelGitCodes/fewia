"""FastAPI application entry point."""

import os
from http import HTTPStatus
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.chat import router as chat_router
from app.api.evidence import router as evidence_router
from app.api.grocery import router as grocery_router
from app.api.kroger import router as kroger_router
from app.api.plan_templates import router as plan_templates_router
from app.api.plans import router as plans_router
from app.api.proposals import router as proposals_router
from app.api.sync import router as sync_router
from app.auth import AuthSettings
from app.deps import get_auth_settings, get_current_user
from app.models import User

_GROCERY_TEMPLATES_PATHS = frozenset(
    {"/grocery/templates", "/grocery/templates/", "/grocery/kroger/stores"}
)
_DEFAULT_ALLOWED_HOSTS = ("localhost", "127.0.0.1", "[::1]", "api")
_ALLOWED_HOSTS_ENV = "FEWIA_ALLOWED_HOSTS"
_API_DOCS_ENV = "FEWIA_API_DOCS"
_INVALID_ALLOWED_HOSTS_MESSAGE = "FEWIA_ALLOWED_HOSTS is invalid."
_ALB_SESSION_COOKIES = (
    "AWSELBAuthSessionCookie",
    "AWSELBAuthSessionCookie-0",
    "AWSELBAuthSessionCookie-1",
    "AWSELBAuthSessionCookie-2",
    "AWSELBAuthSessionCookie-3",
)


class SessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auth_mode: Literal["local_demo", "alb"]
    workspace_id: UUID


class SignoutResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    logout_url: str | None


def grocery_session(
    user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[AuthSettings, Depends(get_auth_settings)],
) -> SessionResponse:
    return SessionResponse(auth_mode=settings.auth_mode, workspace_id=user.workspace_id)


def grocery_signout(
    response: Response,
    user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[AuthSettings, Depends(get_auth_settings)],
) -> SignoutResponse:
    if settings.auth_mode == "alb":
        for name in _ALB_SESSION_COOKIES:
            response.delete_cookie(
                name, path="/", secure=True, httponly=True, samesite="lax"
            )
        return SignoutResponse(logout_url=settings.auth_logout_url)
    return SignoutResponse(logout_url=None)


def allowed_hosts(value: str | None) -> list[str]:
    """Return the default allowed hosts plus the comma-separated extra hosts."""
    hosts = list(_DEFAULT_ALLOWED_HOSTS)
    if value is None:
        return hosts
    for entry in value.split(","):
        host = entry.strip()
        if not host:
            continue
        if "*" in host or "/" in host or any(char.isspace() for char in host):
            raise ValueError(_INVALID_ALLOWED_HOSTS_MESSAGE)
        if ":" in host and host != "[::1]":
            raise ValueError(_INVALID_ALLOWED_HOSTS_MESSAGE)
        hosts.append(host.lower())
    return hosts


def _is_port(text: str) -> bool:
    """Return whether the text is 1 to 5 ASCII digits."""
    return 1 <= len(text) <= 5 and text.isascii() and text.isdigit()


def host_name(value: str) -> str | None:
    """Return the lower-case host name of a Host header value, or None."""
    value = value.lower()
    if any(char in "/@ " or ord(char) < 32 or ord(char) == 127 for char in value):
        return None
    if value.startswith("["):
        end = value.find("]")
        if end == -1:
            return None
        name, rest = value[: end + 1], value[end + 1 :]
    else:
        name, _, rest = value.partition(":")
        if rest:
            rest = f":{rest}"
        elif value.endswith(":"):
            return None
        if not name:
            return None
    if rest and not (rest.startswith(":") and _is_port(rest[1:])):
        return None
    return name


class HostCheckMiddleware:
    """Reject HTTP and WebSocket requests whose Host header is not allowed."""

    def __init__(self, app: ASGIApp, allowed_hosts: list[str]) -> None:
        self.app = app
        self.allowed = frozenset(host.lower() for host in allowed_hosts)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        values = [value for key, value in scope["headers"] if key.lower() == b"host"]
        name = host_name(values[0].decode("latin-1")) if len(values) == 1 else None
        if name is not None and name in self.allowed:
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        response = JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "bad_request",
                    "message": "The Host header is not allowed.",
                }
            },
        )
        await response(scope, receive, send)


def _http_error_code(status_code: int) -> str:
    """Return a stable error code for an HTTP status."""
    try:
        return HTTPStatus(status_code).name.lower()
    except ValueError:
        return f"http_{status_code}"


async def starlette_http_error_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Return Starlette HTTP errors with the API error envelope."""
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content={
            "error": {
                "code": _http_error_code(exc.status_code),
                "message": str(exc.detail),
            }
        },
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return request validation errors with the API error envelope."""
    detail = (
        []
        if request.url.path in _GROCERY_TEMPLATES_PATHS
        else jsonable_encoder(exc.errors())
    )
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "The request has invalid parameters.",
                "detail": detail,
            }
        },
    )


def healthz() -> dict[str, str]:
    """Report that the API process runs."""
    return {"status": "ok"}


def create_app() -> FastAPI:
    """Build the API with its handlers, routes, and host check."""
    hosts = allowed_hosts(os.environ.get(_ALLOWED_HOSTS_ENV))
    docs_enabled = os.environ.get(_API_DOCS_ENV) == "1"
    application = FastAPI(
        title="FEWIA API",
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    application.add_middleware(HostCheckMiddleware, allowed_hosts=hosts)
    application.exception_handler(StarletteHTTPException)(starlette_http_error_handler)
    application.exception_handler(RequestValidationError)(validation_error_handler)
    application.add_api_route("/healthz", healthz, methods=["GET"])
    application.add_api_route("/grocery/session", grocery_session, methods=["GET"])
    application.add_api_route("/grocery/signout", grocery_signout, methods=["POST"])
    for router in (
        grocery_router,
        kroger_router,
        plan_templates_router,
        plans_router,
        proposals_router,
        chat_router,
        evidence_router,
        sync_router,
    ):
        application.include_router(router, dependencies=[Depends(get_current_user)])
    return application


app = create_app()
