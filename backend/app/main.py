"""FastAPI application entry point."""

from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.chat import router as chat_router
from app.api.evidence import router as evidence_router
from app.api.grocery import router as grocery_router
from app.api.kroger import router as kroger_router
from app.api.plan_templates import router as plan_templates_router
from app.api.plans import router as plans_router
from app.api.proposals import router as proposals_router
from app.api.sync import router as sync_router

app = FastAPI(title="FEWIA API")
_GROCERY_TEMPLATES_PATHS = frozenset(
    {"/grocery/templates", "/grocery/templates/", "/grocery/kroger/stores"}
)


def _http_error_code(status_code: int) -> str:
    """Return a stable error code for an HTTP status."""
    try:
        return HTTPStatus(status_code).name.lower()
    except ValueError:
        return f"http_{status_code}"


@app.exception_handler(StarletteHTTPException)
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


@app.exception_handler(RequestValidationError)
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


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Report that the API process runs."""
    return {"status": "ok"}


app.include_router(grocery_router)
app.include_router(kroger_router)
app.include_router(plan_templates_router)
app.include_router(plans_router)
app.include_router(proposals_router)
app.include_router(chat_router)
app.include_router(evidence_router)
app.include_router(sync_router)
