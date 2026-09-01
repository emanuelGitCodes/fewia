"""FastAPI dependencies."""

from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.db import SessionLocal


def get_session() -> Iterator[Session]:
    """Yield a database session and close it after the request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
