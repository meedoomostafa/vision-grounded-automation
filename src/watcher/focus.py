from __future__ import annotations

import ctypes
import os
import time
from dataclasses import dataclass
from threading import Event, Thread
from ctypes import wintypes

import psutil

from src import config
from src.automation.control import ExecutionGate
from src.core.logger import get_logger

logger = get_logger(__name__)
_USER32 = ctypes.windll.user32

_USER32.GetForegroundWindow.restype = wintypes.HWND
_USER32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
_USER32.GetWindowTextLengthW.restype = ctypes.c_int
_USER32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_USER32.GetWindowTextW.restype = ctypes.c_int
_USER32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_USER32.GetClassNameW.restype = ctypes.c_int
_USER32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_USER32.GetWindowThreadProcessId.restype = wintypes.DWORD

try:
    import pywinctl
except Exception:  # pragma: no cover - optional helper
    pywinctl = None

BLACKLISTED_PROCESSES = {
    "code.exe",
    "cmd.exe",
    "conhost.exe",
    "explorer.exe",
    "powershell.exe",
    "pwsh.exe",
    "python.exe",
    "shellexperiencehost.exe",
    "startmenuexperiencehost.exe",
    "taskmgr.exe",
    "uv.exe",
    "windowsterminal.exe",
}

POPUP_KEYWORDS = (
    "alert",
    "confirm",
    "dialog",
    "error",
    "message",
    "notification",
    "popup",
    "save",
    "security",
    "update",
    "warning",
)

DIALOG_CLASS_NAMES = {"#32770"}


@dataclass(frozen=True)
class FocusEvent:
    hwnd: int
    pid: int
    title: str
    class_name: str
    process_name: str
    timestamp: float


class FocusWatcher(Thread):
    """Foreground-window watcher with blacklist and debounce safeguards."""

    def __init__(
        self,
        gate: ExecutionGate,
        on_anomaly,
        *,
        poll_interval: float | None = None,
        debounce_seconds: float | None = None,
        blacklist: set[str] | None = None,
    ) -> None:
        super().__init__(name="focus-watcher", daemon=True)
        self._gate = gate
        self._on_anomaly = on_anomaly
        self._poll_interval = poll_interval or config.FOCUS_POLL_INTERVAL_SECONDS
        self._debounce_seconds = debounce_seconds or config.FOCUS_DEBOUNCE_SECONDS
        self._blacklist = {name.lower() for name in (blacklist or BLACKLISTED_PROCESSES)}
        self._stop_event = Event()
        self._last_signature: tuple[int, int, str] | None = None
        self._last_trigger_at = 0.0
        self._self_pid = os.getpid()

    def stop(self) -> None:
        self._stop_event.set()
        self._gate.resume("watcher stopped")

    def run(self) -> None:  # pragma: no cover - exercised through live run
        logger.info(
            "Focus watcher started with debounce=%.1fs poll=%.2fs",
            self._debounce_seconds,
            self._poll_interval,
        )

        while not self._stop_event.wait(self._poll_interval):
            event = self._snapshot_foreground_window()
            if event is None:
                continue

            signature = (event.hwnd, event.pid, event.title)
            if signature == self._last_signature:
                continue
            self._last_signature = signature

            if not self._gate.is_armed:
                continue
            if event.pid == self._self_pid or self._is_blacklisted(event.process_name):
                continue
            if self._gate.is_expected_title(event.title):
                continue
            if not self._looks_like_popup(event):
                logger.debug(
                    "Ignoring unexpected non-popup focus: title=%r process=%s class=%s",
                    event.title,
                    event.process_name,
                    event.class_name,
                )
                continue

            now = time.monotonic()
            if now - self._last_trigger_at < self._debounce_seconds:
                logger.info(
                    "Debounced focus anomaly for %r (%s)",
                    event.title,
                    event.process_name,
                )
                continue

            self._last_trigger_at = now
            self._gate.pause(
                f"focus stolen by {event.process_name} ({event.title or '<untitled>'})"
            )
            try:
                self._on_anomaly(event)
            except Exception:
                logger.exception("Focus anomaly handler failed")
            finally:
                self._gate.resume("focus anomaly handled")

        logger.info("Focus watcher stopped")

    def _snapshot_foreground_window(self) -> FocusEvent | None:
        hwnd = _USER32.GetForegroundWindow()
        if not hwnd:
            return None

        title = _window_text(hwnd)
        class_name = _class_name(hwnd)
        pid = _window_pid(hwnd)
        process_name = self._get_process_name(pid)

        if not title and pywinctl is not None:
            try:
                active = pywinctl.getActiveWindow()
                if active and getattr(active, "title", ""):
                    title = active.title.strip()
            except Exception:
                pass

        return FocusEvent(
            hwnd=hwnd,
            pid=pid,
            title=title,
            class_name=class_name,
            process_name=process_name,
            timestamp=time.monotonic(),
        )

    @staticmethod
    def _get_process_name(pid: int) -> str:
        try:
            return psutil.Process(pid).name().lower()
        except psutil.Error:
            return "<unknown>"

    def _is_blacklisted(self, process_name: str) -> bool:
        return process_name.lower() in self._blacklist

    @staticmethod
    def _looks_like_popup(event: FocusEvent) -> bool:
        lowered_title = event.title.lower()
        if event.class_name in DIALOG_CLASS_NAMES:
            return True
        if event.process_name == "notepad.exe":
            return True
        return any(keyword in lowered_title for keyword in POPUP_KEYWORDS)


def _window_text(hwnd: int) -> str:
    length = _USER32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    _USER32.GetWindowTextW(hwnd, buffer, len(buffer))
    return buffer.value.strip()


def _class_name(hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    _USER32.GetClassNameW(hwnd, buffer, len(buffer))
    return buffer.value.strip()


def _window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    _USER32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)
