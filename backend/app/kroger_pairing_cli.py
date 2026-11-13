"""Issue a short-lived pairing ticket for the local demo operator."""

import argparse
import sys
from collections.abc import Sequence
from urllib.parse import quote

from sqlalchemy import Connection, Engine, select
from sqlalchemy.exc import SQLAlchemyError

from app.auth import AuthConfigurationError, load_auth_settings
from app.db import SessionLocal
from app.deps import get_kroger_pairing_cipher
from app.models import User
from app.provider_settings import ProviderConfigurationError, load_provider_settings
from app.services.kroger_security import SecurityIntentError, issue_pairing_ticket


def _local_database(bind: Engine | Connection) -> bool:
    url = bind.engine.url
    if bind.dialect.name == "sqlite":
        return True
    return (
        bind.dialect.name == "postgresql"
        and url.host in {"localhost", "127.0.0.1", "::1", "postgres"}
        and not {"host", "hostaddr", "service"}.intersection(url.query)
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.kroger_pairing_cli")
    parser.add_argument("--user-id", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        auth = load_auth_settings()
        settings = load_provider_settings()
        if (
            auth.auth_mode != "local_demo"
            or auth.database_mode != "local"
            or auth.transport_mode != "local"
            or settings.kroger_mode != "live"
            or args.user_id != 1
            or get_kroger_pairing_cipher() is None
        ):
            raise SecurityIntentError()
        with SessionLocal() as session:
            if not _local_database(session.get_bind()):
                raise SecurityIntentError()
            owner = session.scalar(
                select(User).where(User.id == args.user_id, User.status == "active")
            )
            if owner is None:
                raise SecurityIntentError()
            ticket = issue_pairing_ticket(session, owner.id)
            session.commit()
    except (
        AuthConfigurationError,
        ProviderConfigurationError,
        SecurityIntentError,
        SQLAlchemyError,
    ):
        print("Kroger pairing is unavailable.", file=sys.stderr)
        return 2
    print("#kroger-pair=" + quote(ticket, safe=""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
