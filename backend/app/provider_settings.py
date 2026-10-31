"""Load grocery provider settings and local secret files."""

import json
import re
import unicodedata
from pathlib import Path
from typing import Literal, NoReturn, Self
from urllib.parse import urlsplit

from pydantic import SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.budget import SpendingSource

_MAX_FILE_BYTES = 65536
_GUARDRAIL_ID = re.compile(
    r"[a-z0-9]{12}|arn:aws:bedrock:[a-z0-9-]+:[0-9]{12}:guardrail/[a-z0-9]{12}"
)
_GUARDRAIL_VERSION = re.compile(r"DRAFT|[1-9][0-9]{0,5}")


class ProviderConfigurationError(Exception):
    def __init__(self) -> None:
        super().__init__("Provider configuration is invalid")


def _invalid() -> NoReturn:
    raise ProviderConfigurationError()


def _has_control(value: str) -> bool:
    return any(unicodedata.category(ch) == "Cc" or ch == "\x7f" for ch in value)


class GroceryProviderSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FEWIA_", extra="ignore", frozen=True, env_file=None
    )

    spending_source: SpendingSource = "manual"
    bedrock_model_id: str | None = None
    bedrock_region: Literal["us-east-1", "us-west-2"] = "us-east-1"
    aws_profile: str | None = None
    bedrock_prompt_cache: bool = False
    bedrock_guardrail_id: str | None = None
    bedrock_guardrail_version: str | None = None
    plaid_client_id: SecretStr | None = None
    plaid_secret_file: Path | None = None
    plaid_tokens_file: Path | None = None
    usda_fdc_key_file: Path | None = None
    kroger_client_id_file: Path | None = None
    kroger_secret_file: Path | None = None
    kroger_environment: Literal["certification", "production"] = "certification"
    kroger_token_key_file: Path | None = None
    kroger_redirect_uri: str = "http://localhost:8010/grocery/kroger/callback"
    kroger_return_url: str = "http://127.0.0.1:5173/prototype"

    @field_validator("kroger_redirect_uri", "kroger_return_url")
    @classmethod
    def _require_absolute_http_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if (
            parts.scheme not in ("http", "https")
            or not parts.hostname
            or parts.fragment
            or _has_control(value)
            or value != value.strip()
        ):
            raise ValueError("URL MUST be absolute http or https without a fragment")
        return value

    @field_validator("kroger_return_url")
    @classmethod
    def _forbid_return_url_query(cls, value: str) -> str:
        if urlsplit(value).query or value.endswith("?"):
            raise ValueError("return URL MUST NOT have a query string")
        return value

    @field_validator("bedrock_model_id", "aws_profile", mode="before")
    @classmethod
    def _normalize_label(cls, value: object) -> str | None:
        if value is None:
            return None
        stripped = value.strip() if isinstance(value, str) else ""
        if not stripped or len(stripped) > 256:
            raise ValueError("value MUST be nonblank and at most 256 characters")
        return stripped

    @field_validator("bedrock_guardrail_id", "bedrock_guardrail_version", mode="before")
    @classmethod
    def _blank_guardrail_is_unset(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("bedrock_guardrail_id")
    @classmethod
    def _check_guardrail_id(cls, value: str | None) -> str | None:
        if value is not None and not _GUARDRAIL_ID.fullmatch(value):
            raise ValueError("guardrail ID is malformed")
        return value

    @field_validator("bedrock_guardrail_version")
    @classmethod
    def _check_guardrail_version(cls, value: str | None) -> str | None:
        if value is not None and not _GUARDRAIL_VERSION.fullmatch(value):
            raise ValueError("guardrail version is malformed")
        return value

    @model_validator(mode="after")
    def _guardrail_both_or_neither(self) -> Self:
        if (self.bedrock_guardrail_id is None) != (
            self.bedrock_guardrail_version is None
        ):
            raise ValueError("guardrail ID and version go together")
        return self

    @field_validator("plaid_client_id", mode="before")
    @classmethod
    def _normalize_client_id(cls, value: object) -> SecretStr | None:
        if value is None:
            return None
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if not isinstance(raw, str):
            raise ValueError("plaid_client_id MUST be a string")
        stripped = raw.strip()
        if not stripped or _has_control(stripped):
            raise ValueError("plaid_client_id MUST be a nonblank secret")
        return SecretStr(stripped)

    @field_validator(
        "plaid_secret_file",
        "plaid_tokens_file",
        "usda_fdc_key_file",
        "kroger_client_id_file",
        "kroger_secret_file",
        "kroger_token_key_file",
        mode="before",
    )
    @classmethod
    def _normalize_path(cls, value: object) -> Path | None:
        if value is None:
            return None
        if not isinstance(value, Path | str):
            raise ValueError("path MUST be a path string")
        stripped = str(value).strip()
        if not stripped:
            raise ValueError("path MUST be a nonblank string")
        return Path(stripped)


def load_provider_settings() -> GroceryProviderSettings:
    loaded: GroceryProviderSettings | None = None
    try:
        loaded = GroceryProviderSettings()
    except ValidationError:
        pass
    if loaded is None:
        _invalid()
    return loaded


def _read_bounded_utf8(path: Path) -> str:
    payload: bytes | None = None
    try:
        with path.open("rb") as handle:
            payload = handle.read(_MAX_FILE_BYTES + 1)
    except (OSError, ValueError):
        pass
    if payload is None or len(payload) > _MAX_FILE_BYTES:
        _invalid()
    text: str | None = None
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        pass
    if text is None:
        _invalid()
    return text


def read_secret_file(path: Path) -> SecretStr:
    stripped = _read_bounded_utf8(path).strip()
    if not stripped or _has_control(stripped):
        _invalid()
    return SecretStr(stripped)


def load_kroger_credentials(
    settings: GroceryProviderSettings,
) -> tuple[SecretStr, SecretStr]:
    if settings.kroger_client_id_file is None or settings.kroger_secret_file is None:
        _invalid()
    return (
        read_secret_file(settings.kroger_client_id_file),
        read_secret_file(settings.kroger_secret_file),
    )


def _load_token_mapping(path: Path) -> dict[str, str]:
    payload: object | None = None
    try:
        payload = json.loads(_read_bounded_utf8(path))
    except (json.JSONDecodeError, RecursionError):
        pass
    if not isinstance(payload, dict):
        _invalid()
    mapping: dict[str, str] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not key or not isinstance(value, str):
            _invalid()
        token = value.strip()
        if not token or _has_control(token):
            _invalid()
        mapping[key] = token
    return mapping


class TokenFileResolver:
    def __init__(self, path: Path) -> None:
        self._path = path

    def __call__(self, credential_ref: str) -> str:
        if not isinstance(credential_ref, str) or not credential_ref:
            _invalid()
        token = _load_token_mapping(self._path).get(credential_ref)
        if token is None:
            _invalid()
        return token
