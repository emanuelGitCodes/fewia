import ipaddress
import re
from datetime import datetime
from typing import cast

from deployment_config import DeploymentConfig

_ERROR = "preflight metadata is invalid"
_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_REPOSITORY = r"[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*"
_TIMESTAMP = (
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]"
    r"(?:\.[0-9]+)?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])"
)


class PreflightError(RuntimeError):
    """The metadata does not satisfy the preflight contract."""


def _object(raw: object) -> dict[str, object]:
    if type(raw) is not dict:
        raise PreflightError(_ERROR)
    values = cast(dict[object, object], raw)
    if any(type(key) is not str for key in values):
        raise PreflightError(_ERROR)
    return cast(dict[str, object], values)


def _string(raw: object) -> str:
    if type(raw) is not str:
        raise PreflightError(_ERROR)
    return raw


def _san(raw: object) -> str:
    name = _string(raw)
    if not name.isascii():
        raise PreflightError(_ERROR)
    name = name.lower()
    domain = name[2:] if name.startswith("*.") else name
    if len(name) > 253 or re.fullmatch(rf"{_LABEL}(?:\.{_LABEL})*", domain) is None:
        raise PreflightError(_ERROR)
    address = None
    try:
        address = ipaddress.ip_address(domain)
    except ValueError:
        pass
    if address is not None:
        raise PreflightError(_ERROR)
    return name


def _timestamp(raw: object) -> datetime:
    value = _string(raw)
    if re.fullmatch(_TIMESTAMP, value) is None:
        raise PreflightError(_ERROR)
    result = None
    try:
        result = datetime.fromisoformat(value)
    except ValueError:
        pass
    if result is None or result.utcoffset() is None:
        raise PreflightError(_ERROR)
    return result


def check_caller(config: DeploymentConfig, response: object) -> None:
    if _string(_object(response).get("Account")) != config.account:
        raise PreflightError(_ERROR)


def check_certificate(
    config: DeploymentConfig, response: object, *, now: datetime
) -> None:
    """Check metadata. Chain trust and the deployed TLS handshake need separate checks."""
    runtime = config.runtime
    if runtime is None or type(now) is not datetime or now.utcoffset() is None:
        raise PreflightError(_ERROR)
    certificate = _object(_object(response).get("Certificate"))
    if (
        _string(certificate.get("CertificateArn")) != runtime.certificate_arn
        or _string(certificate.get("Status")) != "ISSUED"
        or _string(certificate.get("Type")) not in ("AMAZON_ISSUED", "IMPORTED")
    ):
        raise PreflightError(_ERROR)
    raw_names = certificate.get("SubjectAlternativeNames")
    if type(raw_names) is not list or not raw_names:
        raise PreflightError(_ERROR)
    names = [_san(name) for name in cast(list[object], raw_names)]
    hostname = runtime.hostname.lower()
    if not any(
        name == hostname
        or (name.startswith("*.") and hostname.partition(".")[2] == name[2:])
        for name in names
    ):
        raise PreflightError(_ERROR)
    before = _timestamp(certificate.get("NotBefore"))
    after = _timestamp(certificate.get("NotAfter"))
    if not before <= now < after:
        raise PreflightError(_ERROR)


def check_image(
    config: DeploymentConfig,
    response: object,
    *,
    repository_name: str,
    digest: str,
) -> None:
    """Check image existence. Architecture and scan results need separate checks."""
    repository_name = _string(repository_name)
    digest = _string(digest)
    if (
        not 2 <= len(repository_name) <= 256
        or re.fullmatch(_REPOSITORY, repository_name) is None
        or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
    ):
        raise PreflightError(_ERROR)
    details = _object(response).get("imageDetails")
    if type(details) is not list or len(details) != 1:
        raise PreflightError(_ERROR)
    image = _object(cast(list[object], details)[0])
    if (
        _string(image.get("imageDigest")) != digest
        or _string(image.get("repositoryName")) != repository_name
        or _string(image.get("registryId")) != config.account
    ):
        raise PreflightError(_ERROR)
