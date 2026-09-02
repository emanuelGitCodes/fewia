"""FastAPI application entry point."""

from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import router as context_router
from app.api.predict import router as predict_router
from app.tools.base import ToolError

app = FastAPI(title="FEWIA API")


def _http_error_code(status_code: int) -> str:
    """Return a stable error code for an HTTP status."""
    try:
        return HTTPStatus(status_code).name.lower()
    except ValueError:
        return f"http_{status_code}"


@app.exception_handler(ToolError)
async def tool_error_handler(request: Request, exc: ToolError) -> JSONResponse:
    """Return the tool error code and message with its HTTP status."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


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
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "The request has invalid parameters.",
                "detail": jsonable_encoder(exc.errors()),
            }
        },
    )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Report that the API process runs."""
    return {"status": "ok"}


app.include_router(context_router)
app.include_router(predict_router)
