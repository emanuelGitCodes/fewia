import hashlib
import os
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, NamedTuple, Self

from app.evaluation_io_json import canonical_json_bytes
from app.evaluation_io_json import load_json as load_json

FILE_UNAVAILABLE = "evaluation files are unavailable"
OUTPUT_EXISTS = "evaluation output already exists"


class EvaluationPaths(NamedTuple):
    report: Path
    markdown: Path
    completion: Path


def _emit(handle: BinaryIO, data: bytes) -> None:
    remaining = memoryview(data)
    while remaining:
        written = handle.write(remaining)
        if written is None or written <= 0:
            raise OSError(FILE_UNAVAILABLE)
        remaining = remaining[written:]
    handle.flush()
    os.fsync(handle.fileno())


class EvaluationOutput:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._journal: BinaryIO | None = None
        self._started = False

    def __enter__(self) -> Self:
        if self._started:
            raise OSError(OUTPUT_EXISTS) from None
        self._started = True
        try:
            self.directory.mkdir()
            self._journal = (self.directory / "slots.jsonl").open("x+b", buffering=0)
        except FileExistsError:
            raise OSError(OUTPUT_EXISTS) from None
        except OSError:
            raise OSError(FILE_UNAVAILABLE) from None
        return self

    def _close(self) -> None:
        handle, self._journal = self._journal, None
        if handle is not None:
            try:
                handle.flush()
                os.fsync(handle.fileno())
            finally:
                handle.close()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            self._close()
        except OSError:
            if exc_type is None:
                raise OSError(FILE_UNAVAILABLE) from None

    def append_slot(self, slot: dict[str, object]) -> None:
        handle = self._journal
        if handle is None:
            raise OSError(FILE_UNAVAILABLE) from None
        offset: int | None = None
        try:
            offset = handle.tell()
            data = canonical_json_bytes(slot) + b"\n"
            _emit(handle, data)
        except BaseException as error:
            try:
                if offset is not None:
                    handle.seek(offset)
                    handle.truncate()
                handle.flush()
                os.fsync(handle.fileno())
            except OSError:
                pass
            finally:
                try:
                    self._close()
                except OSError:
                    pass
            if isinstance(error, ValueError):
                raise ValueError("evaluation JSON is invalid") from None
            if isinstance(error, Exception):
                raise OSError(FILE_UNAVAILABLE) from None
            raise

    def _write(self, path: Path, data: bytes) -> str:
        with path.open("x+b", buffering=0) as handle:
            _emit(handle, data)
            handle.seek(0)
            return hashlib.sha256(handle.read()).hexdigest()

    def finish(self, report: dict[str, object], markdown: str) -> EvaluationPaths:
        handle = self._journal
        if handle is None:
            raise OSError(FILE_UNAVAILABLE) from None
        paths = EvaluationPaths(
            self.directory / "report.json",
            self.directory / "report.md",
            self.directory / "completion.json",
        )
        try:
            report_data = canonical_json_bytes(report)
            markdown_data = markdown.encode("utf-8")
            handle.flush()
            os.fsync(handle.fileno())
            handle.seek(0)
            slots = 0
            for line in handle:
                if not line.endswith(b"\n"):
                    raise OSError(FILE_UNAVAILABLE)
                slots += 1
            self._close()
            hashes = {
                "report.json": self._write(paths.report, report_data),
                "report.md": self._write(paths.markdown, markdown_data),
            }
            marker = canonical_json_bytes({"sha256": hashes, "slot_count": slots})
            pending = self.directory / "completion.pending"
            self._write(pending, marker)
            os.link(pending, paths.completion, follow_symlinks=False)
        except BaseException as error:
            try:
                self._close()
            except OSError:
                pass
            if isinstance(error, FileExistsError):
                raise OSError(OUTPUT_EXISTS) from None
            if isinstance(error, ValueError):
                raise ValueError("evaluation JSON is invalid") from None
            if isinstance(error, Exception):
                raise OSError(FILE_UNAVAILABLE) from None
            raise
        return paths
