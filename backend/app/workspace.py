"""Check workspace preconditions for authenticated requests."""

from uuid import UUID

from fastapi import Request
from starlette.types import Scope

from app.models import User

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class WorkspaceChangedError(Exception):
    def __init__(self) -> None:
        super().__init__("Your workspace changed. Reload before continuing.")


def is_browser_request(scope: Scope) -> bool:
    return any(
        name.lower() == b"origin" or name.lower().startswith(b"sec-fetch-")
        for name, _ in scope["headers"]
    )


def check_workspace(request: Request, user: User | None) -> None:
    if request.scope["method"] == "GET" and request.scope["path"] == "/grocery/session":
        return
    values = [
        value
        for name, value in request.scope["headers"]
        if name.lower() == b"x-fewia-workspace"
    ]
    if not values:
        if request.scope["method"] in UNSAFE_METHODS and is_browser_request(
            request.scope
        ):
            raise WorkspaceChangedError()
        return
    if len(values) != 1 or len(values[0]) != 36:
        raise WorkspaceChangedError()
    try:
        value = values[0].decode("ascii")
        workspace_id = UUID(value)
    except (UnicodeDecodeError, ValueError):
        raise WorkspaceChangedError() from None
    if str(workspace_id) != value or user is None or workspace_id != user.workspace_id:
        raise WorkspaceChangedError()
