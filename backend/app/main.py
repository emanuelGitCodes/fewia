"""FastAPI application entry point."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import router as context_router
from app.api.predict import router as predict_router
from app.tools.base import ToolError

app = FastAPI(title="FEWIA API")


@app.exception_handler(ToolError)
async def tool_error_handler(request: Request, exc: ToolError) -> JSONResponse:
    """Return the tool error code and message with its HTTP status."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Report that the API process runs."""
    return {"status": "ok"}


app.include_router(context_router)
app.include_router(predict_router)
