import configparser
import os
import stat
import subprocess
from pathlib import Path
from typing import NoReturn

ERROR_MESSAGE = "Unable to validate the Bedrock runtime credentials."
PROFILE = "fewia-bedrock-runtime"
REQUIRED_KEYS = frozenset({"aws_access_key_id", "aws_secret_access_key"})
SOURCE_ROOT = Path(__file__).resolve().parent.parent
_STRIP_PREFIXES = ("AWS_", "FEWIA_BEDROCK_")
_STRIP_KEYS = frozenset({"FEWIA_AWS_PROFILE"})


def default_credential_path() -> Path:
    return Path.home() / ".config" / "fewia" / "bedrock" / "runtime-credentials"


def _fail(*, path_error: bool = False) -> NoReturn:
    if path_error:
        raise ValueError(ERROR_MESSAGE)
    raise RuntimeError(ERROR_MESSAGE)


def _resolve(path: Path) -> Path:
    try:
        return path.expanduser().resolve(strict=True)
    except OSError:
        _fail(path_error=True)


def _provenance_env() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GIT_", *_STRIP_PREFIXES)) and key not in _STRIP_KEYS
    }


def _git_identity(root: Path) -> tuple[Path, Path]:
    cmd = ["git", "-C", str(root), "rev-parse"]
    cmd += ["--path-format=absolute", "--show-toplevel", "--git-common-dir"]
    try:
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            env=_provenance_env(),
            shell=False,
        )
        lines = result.stdout.splitlines()
        if result.returncode != 0 or len(lines) != 2:
            _fail()
        top = Path(lines[0]).resolve(strict=True)
        common = Path(lines[1]).resolve(strict=True)
    except OSError:
        raise RuntimeError(ERROR_MESSAGE) from None
    return top, common


def validate_checkout(checkout: Path, source_root: Path = SOURCE_ROOT) -> Path:
    resolved_checkout = _resolve(checkout)
    resolved_source = _resolve(source_root)
    if not (resolved_checkout / "compose.yaml").is_file():
        _fail(path_error=True)
    if resolved_checkout == resolved_source:
        return resolved_checkout
    checkout_top, checkout_common = _git_identity(resolved_checkout)
    _, source_common = _git_identity(resolved_source)
    if checkout_top != resolved_checkout or checkout_common != source_common:
        _fail()
    return resolved_checkout


def validate_runtime_credentials(
    checkout: Path,
    credential_path: Path | None = None,
    *,
    source_root: Path = SOURCE_ROOT,
) -> Path:
    path = credential_path or default_credential_path()
    if not path.is_absolute():
        _fail(path_error=True)
    cursor = path
    while True:
        if cursor.is_symlink():
            _fail()
        parent = cursor.parent
        if parent == cursor:
            break
        cursor = parent
    try:
        info = path.lstat()
        parent_info = path.parent.lstat()
        real_file = path.resolve(strict=True)
        checkout_root = _resolve(checkout)
        source = _resolve(source_root)
    except OSError:
        raise RuntimeError(ERROR_MESSAGE) from None
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
        or not stat.S_ISDIR(parent_info.st_mode)
        or parent_info.st_mode & 0o077
        or real_file == checkout_root
        or checkout_root in real_file.parents
        or real_file == source
        or source in real_file.parents
    ):
        _fail()
    try:
        text = path.read_text(encoding="utf-8")
        parser = configparser.RawConfigParser(interpolation=None)
        parser.read_string(text)
    except (OSError, UnicodeError, configparser.Error):
        raise RuntimeError(ERROR_MESSAGE) from None
    section = parser[PROFILE] if parser.has_section(PROFILE) else None
    if (
        dict(parser.defaults())
        or parser.sections() != [PROFILE]
        or section is None
        or set(section) != REQUIRED_KEYS
        or not section["aws_access_key_id"].strip()
        or not section["aws_secret_access_key"].strip()
    ):
        _fail()
    return path


def validated_environment(
    checkout: Path,
    credential_path: Path | None = None,
    *,
    source_root: Path = SOURCE_ROOT,
) -> dict[str, str]:
    path = validate_runtime_credentials(
        checkout, credential_path, source_root=source_root
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(_STRIP_PREFIXES) and key not in _STRIP_KEYS
    }
    env["FEWIA_RUNTIME_CREDENTIALS_FILE"] = str(path)
    return env
