from __future__ import annotations

import atexit
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

import psutil

from src.core.exceptions import SingletonLockError
from src.core.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class LockMetadata:
    pid: int
    process_create_time: float
    command: str


def _current_process_metadata() -> LockMetadata:
    process = psutil.Process(os.getpid())
    command = " ".join(process.cmdline()) or process.name()
    return LockMetadata(
        pid=process.pid,
        process_create_time=process.create_time(),
        command=command,
    )


def _is_process_instance_alive(metadata: LockMetadata) -> bool:
    try:
        process = psutil.Process(metadata.pid)
    except psutil.Error:
        return False

    try:
        return abs(process.create_time() - metadata.process_create_time) < 0.001
    except psutil.Error:
        return False


class SingletonLock:

    def __init__(self, path: Path):
        self.path = Path(path)
        self._fd: int | None = None
        self._metadata = _current_process_metadata()
        self._released = True
        atexit.register(self._release_at_exit)

    @property
    def metadata(self) -> LockMetadata:
        return self._metadata

    def acquire(self) -> None:
        if not self._released:
            return

        self.path.parent.mkdir(parents=True, exist_ok=True)

        while True:
            try:
                self._fd = os.open(
                    self.path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
            except FileExistsError:
                existing = self._read_metadata()
                if existing and _is_process_instance_alive(existing):
                    raise SingletonLockError(
                        f"Another automation instance is already running "
                        f"(pid={existing.pid}, command={existing.command})"
                    )

                logger.warning("Removing stale runtime lock at %s", self.path)
                self._remove_lock_file()
                continue

            self._write_metadata()
            self._released = False
            logger.info(
                "Acquired runtime lock at %s for pid=%d",
                self.path,
                self._metadata.pid,
            )
            return

    def release(self) -> None:
        if self._released:
            return

        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

        self._remove_lock_file()
        self._released = True
        logger.info("Released runtime lock at %s", self.path)

    def __enter__(self) -> "SingletonLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()

    def _write_metadata(self) -> None:
        if self._fd is None:
            raise RuntimeError("Lock file descriptor is not available")

        payload = json.dumps(asdict(self._metadata), sort_keys=True).encode("utf-8")
        os.write(self._fd, payload)
        os.fsync(self._fd)

    def _read_metadata(self) -> LockMetadata | None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError):
            return None

        try:
            return LockMetadata(
                pid=int(payload["pid"]),
                process_create_time=float(payload["process_create_time"]),
                command=str(payload.get("command", "")),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def _remove_lock_file(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            return

    def _release_at_exit(self) -> None:
        try:
            self.release()
        except Exception:
            logger.debug("Ignoring lock release failure during interpreter shutdown", exc_info=True)


def acquire_singleton_lock(path: Path) -> SingletonLock:
    lock = SingletonLock(path)
    lock.acquire()
    return lock
