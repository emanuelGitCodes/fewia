"""FastAPI application entry point."""

from fastapi import FastAPI

app = FastAPI(title="FEWIA API")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Report that the API process runs."""
    return {"status": "ok"}
