from __future__ import annotations

import re

from src import config
from src.automation.control import execution_gate
from src.automation.desktop import get_bot, wait_ms
from src.core.logger import get_logger

logger = get_logger(__name__)
_PYWINAUTO_BACKENDS = ("uia", "win32")

try:
    from pywinauto import Desktop
except Exception as exc:                                                  
    Desktop = None
    _PYWINAUTO_IMPORT_ERROR = exc
else:
    _PYWINAUTO_IMPORT_ERROR = None


def _timeout_ms(timeout: int | float | None) -> int:
    seconds = config.WINDOW_TIMEOUT if timeout is None else timeout
    return max(int(seconds * 1000), 250)


def _title_re(title_contains: str) -> str:
    return f".*{re.escape(title_contains)}.*"


def _window_label(window) -> str:
    if hasattr(window, "window_text"):
        try:
            return window.window_text()
        except Exception:
            pass

    title = getattr(window, "title", None)
    if isinstance(title, str) and title:
        return title

    return "<unknown>"


def _window_object(window):
    if hasattr(window, "wrapper_object"):
        try:
            return window.wrapper_object()
        except Exception:
            return window
    return window


def _is_minimized(window) -> bool:
    for attr_name in ("is_minimized", "isMinimized"):
        attr = getattr(window, attr_name, None)
        if callable(attr):
            try:
                return bool(attr())
            except Exception:
                continue
        if attr is not None:
            return bool(attr)
    return False


def _find_window_with_botcity(title_contains: str, timeout_ms: int):
    bot = get_bot()
    selector = {"title_re": _title_re(title_contains)}
    last_error = None

    for backend in _botcity_backends():
        try:
            bot.connect_to_app(backend=backend, timeout=timeout_ms, **selector)
            window = bot.find_app_window(waiting_time=timeout_ms, **selector)
            if window is not None:
                return window
        except Exception as exc:                                               
            last_error = exc

    raise LookupError(
        f"BotCity could not resolve window '{title_contains}': {last_error}"
    ) from last_error


def _find_window_with_pywinauto(title_contains: str, timeout_ms: int):
    if Desktop is None:
        raise LookupError(f"pywinauto is unavailable: {_PYWINAUTO_IMPORT_ERROR}")

    title_re = _title_re(title_contains)
    timeout_seconds = timeout_ms / 1000
    last_error = None

    for pywinauto_backend in _PYWINAUTO_BACKENDS:
        try:
            window = Desktop(backend=pywinauto_backend).window(title_re=title_re)
            window.wait("exists enabled visible ready", timeout=timeout_seconds)
            return window
        except Exception as exc:                                               
            last_error = exc

    raise LookupError(
        f"pywinauto could not resolve window '{title_contains}': {last_error}"
    ) from last_error


def _find_window(title_contains: str, timeout_ms: int):
    try:
        return _find_window_with_botcity(title_contains, timeout_ms)
    except LookupError as botcity_error:
        logger.debug(
            "BotCity window lookup failed for '%s': %s",
            title_contains,
            botcity_error,
        )

    return _find_window_with_pywinauto(title_contains, timeout_ms)


def _botcity_backends():
    try:
        from botcity.core import Backend
    except Exception as exc:
        raise LookupError(f"BotCity backend import failed: {exc}") from exc

    return (
        Backend.UIA,
        Backend.WIN_32,
    )


def wait_for_window(title_contains: str, timeout: int | float | None = None) -> bool:
    if config.DRY_RUN:
        logger.info("[DRY_RUN] wait_for_window('%s') -> True", title_contains)
        return True

    timeout_ms = _timeout_ms(timeout)
    execution_gate.wait_if_paused()
    try:
        window = _find_window(title_contains, timeout_ms)
    except LookupError:
        logger.warning("Window '%s' not found within %dms", title_contains, timeout_ms)
        return False

    logger.debug(
        "Found window matching '%s': %s",
        title_contains,
        _window_label(window),
    )
    return True


def activate_window(title_contains: str, timeout: int | float | None = None) -> bool:
    if config.DRY_RUN:
        logger.info("[DRY_RUN] activate_window('%s') -> True", title_contains)
        return True

    try:
        execution_gate.wait_if_paused()
        window = _window_object(_find_window(title_contains, _timeout_ms(timeout)))
    except LookupError as exc:
        logger.warning("No window found matching '%s': %s", title_contains, exc)
        return False

    try:
        if _is_minimized(window):
            window.restore()
            wait_ms(150)

        if hasattr(window, "set_focus"):
            window.set_focus()
        elif hasattr(window, "activate"):
            window.activate()
        else:
            raise AttributeError("window does not support focus activation")

        logger.debug("Activated window: %s", _window_label(window))
        return True
    except Exception as exc:
        logger.warning("Failed to activate window '%s': %s", title_contains, exc)
        return False


def close_window(title_contains: str, timeout: int | float | None = None) -> bool:
    if config.DRY_RUN:
        logger.info("[DRY_RUN] close_window('%s') -> True", title_contains)
        return True

    try:
        execution_gate.wait_if_paused()
        window = _window_object(_find_window(title_contains, _timeout_ms(timeout)))
    except LookupError:
        return True

    try:
        window.close()
        logger.debug("Closed window: %s", _window_label(window))
        return True
    except Exception as exc:
        logger.warning("Failed to close window '%s': %s", title_contains, exc)
        return False


def is_window_open(title_contains: str) -> bool:
    if config.DRY_RUN:
        return False

    execution_gate.wait_if_paused()
    try:
        _find_window(title_contains, 250)
    except LookupError:
        return False

    return True
