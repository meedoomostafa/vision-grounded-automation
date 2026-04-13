from __future__ import annotations

from contextlib import contextmanager
from threading import Event, RLock
from threading import local

from src.core.logger import get_logger

logger = get_logger(__name__)


class ExecutionGate:

    def __init__(self) -> None:
        self._resume_event = Event()
        self._resume_event.set()
        self._lock = RLock()
        self._armed = False
        self._expected_titles: tuple[str, ...] = ()
        self._pause_reason = ""
        self._local = local()

    def arm(self, expected_titles: tuple[str, ...] | list[str]) -> None:
        with self._lock:
            self._expected_titles = tuple(title for title in expected_titles if title)
            self._armed = True
            logger.debug("Execution gate armed with expected titles: %s", self._expected_titles)

    def disarm(self) -> None:
        with self._lock:
            self._armed = False
            self._expected_titles = ()
            logger.debug("Execution gate disarmed")

    def pause(self, reason: str) -> None:
        with self._lock:
            self._pause_reason = reason
            self._resume_event.clear()
            logger.warning("Automation paused: %s", reason)

    def resume(self, reason: str = "") -> None:
        with self._lock:
            self._pause_reason = ""
            self._resume_event.set()
            if reason:
                logger.info("Automation resumed: %s", reason)

    def wait_if_paused(self) -> None:
        if getattr(self._local, "bypass_pause", False):
            return
        self._resume_event.wait()

    @property
    def is_armed(self) -> bool:
        with self._lock:
            return self._armed

    @property
    def expected_titles(self) -> tuple[str, ...]:
        with self._lock:
            return self._expected_titles

    def is_expected_title(self, title: str) -> bool:
        lowered_title = title.lower()
        return any(expected.lower() in lowered_title for expected in self.expected_titles)

    @contextmanager
    def bypass_pause(self):
        previous = getattr(self._local, "bypass_pause", False)
        self._local.bypass_pause = True
        try:
            yield
        finally:
            self._local.bypass_pause = previous


execution_gate = ExecutionGate()
