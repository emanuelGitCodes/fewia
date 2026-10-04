import re
from dataclasses import dataclass
from typing import Literal, cast

from identity import _validate_hostname, _validate_prefix

REGION = "us-east-1"
_ERROR = "deployment configuration is invalid"
_RUNTIME_FIELDS = frozenset(
    (
        "hostname",
        "domain_prefix",
        "certificate_arn",
        "backend_digest",
        "frontend_digest",
    )
)


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    hostname: str
    domain_prefix: str
    certificate_arn: str
    backend_digest: str
    frontend_digest: str


@dataclass(frozen=True, slots=True)
class DeploymentConfig:
    account: str
    phase: Literal["foundation", "bootstrap", "active"]
    runtime: RuntimeConfig | None


def _dictionary(raw: object) -> dict[str, object]:
    if type(raw) is not dict:
        raise ValueError(_ERROR)
    values = cast(dict[object, object], raw)
    if any(type(key) is not str for key in values):
        raise ValueError(_ERROR)
    return cast(dict[str, object], values)


def _string(raw: object) -> str:
    if type(raw) is not str:
        raise ValueError(_ERROR)
    return raw


def _valid_names(hostname: str, domain_prefix: str) -> bool:
    try:
        _validate_hostname(hostname)
        _validate_prefix(domain_prefix)
    except ValueError:
        return False
    return True


def parse_deployment_config(raw: object) -> DeploymentConfig:
    values = _dictionary(raw)
    if not {"account", "phase"} <= values.keys() or values.keys() - {
        "account",
        "phase",
        "runtime",
    }:
        raise ValueError(_ERROR)
    account = _string(values["account"])
    phase = _string(values["phase"])
    if re.fullmatch(r"[0-9]{12}", account) is None or phase not in (
        "foundation",
        "bootstrap",
        "active",
    ):
        raise ValueError(_ERROR)
    if phase == "foundation":
        if values.get("runtime") is not None:
            raise ValueError(_ERROR)
        return DeploymentConfig(account=account, phase="foundation", runtime=None)
    runtime_values = _dictionary(values.get("runtime"))
    if runtime_values.keys() != _RUNTIME_FIELDS:
        raise ValueError(_ERROR)
    runtime = RuntimeConfig(
        **{field: _string(runtime_values[field]) for field in _RUNTIME_FIELDS}
    )
    if (
        not _valid_names(runtime.hostname, runtime.domain_prefix)
        or re.fullmatch(
            rf"arn:aws:acm:{REGION}:{account}:certificate/"
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            runtime.certificate_arn,
        )
        is None
        or any(
            re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
            for digest in (runtime.backend_digest, runtime.frontend_digest)
        )
    ):
        raise ValueError(_ERROR)
    return DeploymentConfig(
        account=account,
        phase=cast(Literal["bootstrap", "active"], phase),
        runtime=runtime,
    )
