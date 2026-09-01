"""HTTP routes for the deterministic context tools."""

from fastapi import APIRouter

router = APIRouter(prefix="/context", tags=["context"])
