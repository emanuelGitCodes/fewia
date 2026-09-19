import os
import stat
from pathlib import Path
from typing import NoReturn

from infra.bedrock_runtime_validation import SOURCE_ROOT

ERROR_MESSAGE = "Unable to validate the Spoonacular runtime credentials."
_MAX_BYTES = 8192


def _fail(*, path_error: bool = False) -> NoReturn:
    if path_error:
        raise ValueError(ERROR_MESSAGE)
    raise RuntimeError(ERROR_MESSAGE)


def validate_spoonacular_credentials(
    checkout: Path,
    credential_path: Path,
    *,
    source_root: Path = SOURCE_ROOT,
) -> Path:
    if not credential_path.is_absolute():
        _fail(path_error=True)
    cursor = credential_path
    while True:
        if cursor.is_symlink():
            _fail()
        parent = cursor.parent
        if parent == cursor:
            break
        cursor = parent
    try:
        info = credential_path.lstat()
        parent_info = credential_path.parent.lstat()
        real_file = credential_path.resolve(strict=True)
        checkout_root = checkout.expanduser().resolve(strict=True)
        source = source_root.expanduser().resolve(strict=True)
    except OSError:
        raise RuntimeError(ERROR_MESSAGE) from None
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
        or not (info.st_mode & stat.S_IRUSR)
        or info.st_size < 1
        or info.st_size > _MAX_BYTES
        or not stat.S_ISDIR(parent_info.st_mode)
        or parent_info.st_uid != os.getuid()
        or parent_info.st_mode & 0o077
        or real_file == checkout_root
        or checkout_root in real_file.parents
        or real_file == source
        or source in real_file.parents
    ):
        _fail()
    return real_file
