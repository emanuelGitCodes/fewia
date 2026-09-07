"""Plaid Sandbox REST /transactions/sync adapter."""

import json
from collections.abc import Callable
from decimal import Decimal
from typing import NoReturn

import httpx

from app.providers.plaid_contract import SyncPage, parse_sync_page

SANDBOX_BASE_URL = "https://sandbox.plaid.com"
SYNC_URL = "https://sandbox.plaid.com/transactions/sync"
SYNC_COUNT = 500
_MUTATION_CODE = "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION"
_TIMEOUT = httpx.Timeout(20.0, connect=3.0, read=20.0, write=20.0, pool=3.0)


class PlaidUnavailable(Exception):
    def __init__(self) -> None:
        super().__init__("Plaid Sandbox is unavailable")


class PlaidSyncMutation(Exception):
    def __init__(self) -> None:
        super().__init__("Plaid sync mutated during pagination")


def _require_nonblank(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} MUST be a nonblank string")
    return value


def _parse_success(response: httpx.Response) -> SyncPage:
    payload: object | None = None
    try:
        payload = json.loads(response.content, parse_float=Decimal)
    except Exception:
        pass
    return parse_sync_page(payload)


def _mutation_error(response: httpx.Response) -> bool:
    try:
        payload = json.loads(response.content)
    except Exception:
        return False
    if not isinstance(payload, dict):
        return False
    return payload.get("error_code") == _MUTATION_CODE


def _raise_failure(response: httpx.Response) -> NoReturn:
    if _mutation_error(response):
        raise PlaidSyncMutation()
    raise PlaidUnavailable()


class PlaidSandboxProvider:
    def __init__(
        self,
        client_id: str,
        secret: str,
        token_resolver: Callable[[str], str],
        client: httpx.Client | None = None,
    ) -> None:
        self._client_id = _require_nonblank(client_id, "client_id")
        self._secret = _require_nonblank(secret, "secret")
        self._token_resolver = token_resolver
        if client is None:
            self._client = httpx.Client(
                base_url=SANDBOX_BASE_URL,
                timeout=_TIMEOUT,
                follow_redirects=False,
                trust_env=False,
                transport=httpx.HTTPTransport(retries=0, trust_env=False),
            )
            self._owns_client = True
        else:
            self._client = client
            self._owns_client = False

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def sync_page(self, credential_ref: str, cursor: str | None) -> SyncPage:
        _require_nonblank(credential_ref, "credential_ref")
        access_token: str | None = None
        try:
            access_token = _require_nonblank(
                self._token_resolver(credential_ref), "access_token"
            )
        except Exception:
            pass
        if access_token is None:
            raise ValueError("access_token MUST be a nonblank string")
        payload: dict[str, object] = {
            "client_id": self._client_id,
            "secret": self._secret,
            "access_token": access_token,
            "count": SYNC_COUNT,
        }
        if cursor is not None:
            payload["cursor"] = cursor
        response: httpx.Response | None = None
        try:
            response = self._client.post(
                SYNC_URL,
                json=payload,
                follow_redirects=False,
                timeout=_TIMEOUT,
            )
        except httpx.RequestError:
            pass
        if response is None:
            raise PlaidUnavailable()
        if response.status_code != 200:
            _raise_failure(response)
        return _parse_success(response)
